suppressPackageStartupMessages({
  library(DBI)
})

simple_hash6 <- function(x) {
  ints <- utf8ToInt(enc2utf8(x))
  if (length(ints) == 0) {
    return("000000")
  }
  w <- seq_along(ints)
  v <- sum(as.double(ints) * as.double(w))
  sprintf("%06x", as.integer(v %% (16^6)))
}

metric_code <- function(col_name) {
  if (grepl("_count$", col_name)) return("cnt")
  if (grepl("_sum$", col_name)) return("sum")
  if (grepl("(_length_m|_leng|_lengt|_length)$", col_name)) return("len")
  if (grepl("(_area_share|_area_shar|_area_sha|_area_sh|_area_s|_area)$", col_name)) return("shr")
  "val"
}

strip_metric_suffix <- function(col_name) {
  sub("(_count|_sum|_length_m|_leng|_lengt|_length|_area_share|_area_shar|_area_sha|_area_sh|_area_s|_area)$", "", col_name)
}

build_short_name <- function(col_name, metric, max_base = 38) {
  base <- strip_metric_suffix(col_name)
  base <- gsub("[^a-zA-Z0-9_]+", "_", base)
  base <- gsub("_+", "_", base)
  base <- gsub("^_+|_+$", "", base)
  base <- tolower(base)
  if (!nzchar(base)) base <- "feature"
  base <- substr(base, 1, max_base)
  paste0("gc_", base, "_", metric, "_", simple_hash6(col_name))
}

infer_metric_from_geometry <- function(geometry_text) {
  g <- tolower(trimws(geometry_text))
  if (grepl("point", g)) return("cnt")
  if (grepl("line", g)) return("len")
  if (grepl("polygon", g)) return("shr")
  "val"
}

make_unique_names <- function(x) {
  out <- character(length(x))
  seen <- new.env(parent = emptyenv())

  for (i in seq_along(x)) {
    name_i <- x[[i]]
    if (!exists(name_i, envir = seen, inherits = FALSE)) {
      assign(name_i, 1L, envir = seen)
      out[[i]] <- name_i
    } else {
      n <- get(name_i, envir = seen, inherits = FALSE) + 1L
      assign(name_i, n, envir = seen)
      out[[i]] <- paste0(name_i, "_", n)
    }
  }
  out
}

args_full <- commandArgs(trailingOnly = FALSE)
file_arg <- grep("^--file=", args_full, value = TRUE)
if (length(file_arg) > 0) {
  script_file <- normalizePath(sub("^--file=", "", file_arg[1]), winslash = "/", mustWork = TRUE)
  script_dir <- dirname(script_file)
  project_root <- normalizePath(file.path(script_dir, "..", ".."), winslash = "/", mustWork = TRUE)
} else {
  script_dir <- normalizePath("databas/script", winslash = "/", mustWork = FALSE)
  project_root <- normalizePath(".", winslash = "/", mustWork = FALSE)
}

db_connect_candidates <- c(
  file.path(project_root, "databas/generell_databas_setup/R/db_connect.R"),
  file.path(project_root, "generell_databas_setup/R/db_connect.R"),
  file.path(project_root, "speedlocal_bornholm/R/db_connect.R")
)
db_connect_path <- db_connect_candidates[file.exists(db_connect_candidates)][1]
if (is.na(db_connect_path) || !nzchar(db_connect_path)) {
  stop("Could not find db_connect.R. Tried: ", paste(db_connect_candidates, collapse = " | "))
}
source(db_connect_path)

cfg_env <- Sys.getenv("PIPELINE_ENV_PATH", ".env")
schema <- Sys.getenv("PIPELINE_SCHEMA", "h3")
raw_table <- Sys.getenv("GEOCONTEXT_RAW_TABLE", "bornholm_r8_geocontext_raw")
features_table <- Sys.getenv("GEOCONTEXT_FEATURES_TABLE", "bornholm_r8_geocontext_features")
zscores_table <- Sys.getenv("GEOCONTEXT_ZSCORES_TABLE", "bornholm_r8_geocontext_zscores")
mapping_table <- Sys.getenv("GEOCONTEXT_MAPPING_TABLE", "bornholm_r8_geocontext_feature_map")
write_zscores <- tolower(Sys.getenv("WRITE_GEOCONTEXT_ZSCORES", "true")) %in% c("1", "true", "yes")
mapping_csv <- Sys.getenv(
  "GEOCONTEXT_MAPPING_CSV",
  file.path(script_dir, "config/bornholm_r8_geocontext_feature_map.csv")
)
selection_csv <- Sys.getenv(
  "GEOCONTEXT_SELECTION_CSV",
  file.path(script_dir, "config/bornholm_r8_geocontext_layers.csv")
)

con <- connect_pg(cfg_env)
on.exit(DBI::dbDisconnect(con), add = TRUE)

raw_id <- DBI::Id(schema = schema, table = raw_table)
feat_id <- DBI::Id(schema = schema, table = features_table)
z_id <- DBI::Id(schema = schema, table = zscores_table)
map_id <- DBI::Id(schema = schema, table = mapping_table)

if (!DBI::dbExistsTable(con, raw_id)) {
  stop("Raw table missing: ", schema, ".", raw_table)
}

raw_cols <- DBI::dbListFields(con, raw_id)
feature_cols <- setdiff(raw_cols, "hex_id")
if (length(feature_cols) == 0) {
  stop("No feature columns found in: ", schema, ".", raw_table)
}

metric <- vapply(feature_cols, metric_code, character(1))
mapping <- data.frame(
  source_column = feature_cols,
  short_column = NA_character_,
  metric = metric,
  stringsAsFactors = FALSE
)

# If columns were truncated in Postgres, recover metric labels from selection order.
if (file.exists(selection_csv)) {
  sel <- read.csv(selection_csv, stringsAsFactors = FALSE)
  if ("include" %in% names(sel)) {
    sel$include <- as.logical(sel$include)
    sel <- sel[sel$include, , drop = FALSE]
  }
  if (nrow(sel) == nrow(mapping) && "geometry" %in% names(sel)) {
    inferred <- vapply(sel$geometry, infer_metric_from_geometry, character(1))
    needs_fix <- mapping$metric == "val" & inferred %in% c("cnt", "len", "shr")
    mapping$metric[needs_fix] <- inferred[needs_fix]
  }
}

# Fallback inference: columns in [0,1] are almost always area shares.
val_cols <- mapping$source_column[mapping$metric == "val"]
if (length(val_cols) > 0) {
  for (col_i in val_cols) {
    q <- paste0(
      "SELECT MIN(",
      DBI::dbQuoteIdentifier(con, col_i),
      ") AS mn, MAX(",
      DBI::dbQuoteIdentifier(con, col_i),
      ") AS mx FROM ",
      DBI::dbQuoteIdentifier(con, raw_id)
    )
    s <- DBI::dbGetQuery(con, q)
    mn <- s$mn[[1]]
    mx <- s$mx[[1]]
    if (!is.na(mn) && !is.na(mx) && mn >= -1e-9 && mx <= 1 + 1e-9) {
      mapping$metric[mapping$source_column == col_i] <- "shr"
    }
  }
}

mapping$short_column <- mapply(
  build_short_name,
  mapping$source_column,
  mapping$metric,
  USE.NAMES = FALSE
)
mapping$short_column <- make_unique_names(mapping$short_column)

select_parts <- c(
  paste0(
    DBI::dbQuoteIdentifier(con, "hex_id"),
    " AS ",
    DBI::dbQuoteIdentifier(con, "hex_id")
  ),
  mapply(
    function(src, dst) {
      paste0(DBI::dbQuoteIdentifier(con, src), " AS ", DBI::dbQuoteIdentifier(con, dst))
    },
    mapping$source_column,
    mapping$short_column,
    USE.NAMES = FALSE
  )
)

sql_features <- paste0(
  "SELECT ",
  paste(select_parts, collapse = ", "),
  " FROM ",
  DBI::dbQuoteIdentifier(con, raw_id)
)

message("Building feature table: ", schema, ".", features_table)
features_df <- DBI::dbGetQuery(con, sql_features)
DBI::dbWriteTable(con, feat_id, features_df, overwrite = TRUE)
DBI::dbExecute(
  con,
  paste0(
    "CREATE INDEX IF NOT EXISTS ",
    features_table,
    "_hex_id_idx ON ",
    DBI::dbQuoteIdentifier(con, feat_id),
    "(hex_id);"
  )
)

if (write_zscores) {
  z_parts <- c(
    paste0(
      DBI::dbQuoteIdentifier(con, "hex_id"),
      " AS ",
      DBI::dbQuoteIdentifier(con, "hex_id")
    ),
    vapply(
      mapping$short_column,
      function(col_i) {
        qcol <- DBI::dbQuoteIdentifier(con, col_i)
        zcol <- DBI::dbQuoteIdentifier(con, paste0(col_i, "_z"))
        paste0(
          "((",
          qcol,
          " - AVG(",
          qcol,
          ") OVER()) / NULLIF(STDDEV_POP(",
          qcol,
          ") OVER(), 0)) AS ",
          zcol
        )
      },
      character(1)
    )
  )

  sql_z <- paste0(
    "SELECT ",
    paste(z_parts, collapse = ", "),
    " FROM ",
    DBI::dbQuoteIdentifier(con, feat_id)
  )

  message("Building z-score table: ", schema, ".", zscores_table)
  z_df <- DBI::dbGetQuery(con, sql_z)
  DBI::dbWriteTable(con, z_id, z_df, overwrite = TRUE)
  DBI::dbExecute(
    con,
    paste0(
      "CREATE INDEX IF NOT EXISTS ",
      zscores_table,
      "_hex_id_idx ON ",
      DBI::dbQuoteIdentifier(con, z_id),
      "(hex_id);"
    )
  )
}

message("Writing mapping table: ", schema, ".", mapping_table)
DBI::dbWriteTable(con, map_id, mapping, overwrite = TRUE)

dir.create(dirname(mapping_csv), recursive = TRUE, showWarnings = FALSE)
write.csv(mapping, mapping_csv, row.names = FALSE, na = "")

n_raw <- DBI::dbGetQuery(con, paste0("SELECT COUNT(*) AS n FROM ", DBI::dbQuoteIdentifier(con, raw_id)))$n[[1]]
n_feat <- DBI::dbGetQuery(con, paste0("SELECT COUNT(*) AS n FROM ", DBI::dbQuoteIdentifier(con, feat_id)))$n[[1]]

if (!isTRUE(n_raw == n_feat)) {
  stop(sprintf("Row mismatch: %s.%s=%s vs %s.%s=%s", schema, raw_table, n_raw, schema, features_table, n_feat))
}

message("Done. Rows: ", n_feat, " | Features: ", length(feature_cols))
message("Mapping CSV: ", normalizePath(mapping_csv, winslash = "/", mustWork = FALSE))
