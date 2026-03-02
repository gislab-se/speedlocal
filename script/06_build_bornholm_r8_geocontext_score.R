suppressPackageStartupMessages({
  library(DBI)
})

safe_z <- function(x) {
  x <- as.numeric(x)
  m <- mean(x, na.rm = TRUE)
  s <- stats::sd(x, na.rm = TRUE)
  if (is.na(s) || s == 0) {
    return(rep(0, length(x)))
  }
  (x - m) / s
}

apply_transform <- function(x, transform_name) {
  x <- as.numeric(x)
  t <- tolower(trimws(transform_name))
  if (!nzchar(t) || t == "none") return(x)
  if (t == "log1p") return(log1p(pmax(x, 0)))
  if (t == "sqrt") return(sqrt(pmax(x, 0)))
  if (t == "asinh") return(asinh(x))
  warning("Unknown transform '", transform_name, "'. Using none.")
  x
}

to_bool <- function(x) {
  if (is.logical(x)) return(x)
  t <- tolower(trimws(as.character(x)))
  t %in% c("1", "true", "yes", "y")
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
hex_table <- Sys.getenv("HEX_TABLE", "bornholm_r8")
features_table <- Sys.getenv("GEOCONTEXT_FEATURES_TABLE", "bornholm_r8_geocontext_features")
mapping_table <- Sys.getenv("GEOCONTEXT_MAPPING_TABLE", "bornholm_r8_geocontext_feature_map")
score_table <- Sys.getenv("GEOCONTEXT_SCORE_TABLE", "bornholm_r8_geocontext_score")
score_view <- Sys.getenv("GEOCONTEXT_SCORE_VIEW", "v_bornholm_r8_geocontext_score")

score_cfg_csv <- Sys.getenv(
  "GEOCONTEXT_SCORE_CONFIG_CSV",
  file.path(script_dir, "config/bornholm_r8_geocontext_scoring.csv")
)
mapping_csv <- Sys.getenv(
  "GEOCONTEXT_MAPPING_CSV",
  file.path(script_dir, "config/bornholm_r8_geocontext_feature_map.csv")
)

con <- connect_pg(cfg_env)
on.exit(DBI::dbDisconnect(con), add = TRUE)

feat_id <- DBI::Id(schema = schema, table = features_table)
map_id <- DBI::Id(schema = schema, table = mapping_table)
score_id <- DBI::Id(schema = schema, table = score_table)

if (!DBI::dbExistsTable(con, feat_id)) {
  stop("Missing features table: ", schema, ".", features_table)
}

if (file.exists(score_cfg_csv)) {
  cfg <- read.csv(score_cfg_csv, stringsAsFactors = FALSE)
} else {
  if (DBI::dbExistsTable(con, map_id)) {
    mapping <- DBI::dbReadTable(con, map_id)
  } else if (file.exists(mapping_csv)) {
    mapping <- read.csv(mapping_csv, stringsAsFactors = FALSE)
  } else {
    stop("No mapping source found. Expected table ", schema, ".", mapping_table, " or file ", mapping_csv)
  }

  cfg <- data.frame(
    include = TRUE,
    short_column = mapping$short_column,
    source_column = mapping$source_column,
    metric = mapping$metric,
    direction = 1,
    weight = 1,
    transform = "none",
    notes = "",
    stringsAsFactors = FALSE
  )
  cfg$transform[cfg$metric %in% c("cnt")] <- "log1p"

  dir.create(dirname(score_cfg_csv), recursive = TRUE, showWarnings = FALSE)
  write.csv(cfg, score_cfg_csv, row.names = FALSE, na = "")
  message("Wrote default scoring config: ", normalizePath(score_cfg_csv, winslash = "/", mustWork = FALSE))
}

required <- c("include", "short_column", "direction", "weight", "transform")
missing_cols <- setdiff(required, names(cfg))
if (length(missing_cols) > 0) {
  stop("Scoring config missing required columns: ", paste(missing_cols, collapse = ", "))
}

cfg$include <- to_bool(cfg$include)
cfg$direction <- as.numeric(cfg$direction)
cfg$weight <- as.numeric(cfg$weight)
cfg <- cfg[cfg$include & !is.na(cfg$weight) & cfg$weight > 0, , drop = FALSE]

if (nrow(cfg) == 0) {
  stop("No active rows in scoring config. Set include=TRUE and weight>0.")
}

feat <- DBI::dbReadTable(con, feat_id)
if (!("hex_id" %in% names(feat))) {
  stop("Features table missing hex_id.")
}

missing_features <- setdiff(cfg$short_column, names(feat))
if (length(missing_features) > 0) {
  stop("These config features are not in features table: ", paste(missing_features, collapse = ", "))
}

work <- feat["hex_id"]
contrib <- vector("list", nrow(cfg))
sum_w <- sum(cfg$weight)

for (i in seq_len(nrow(cfg))) {
  row_i <- cfg[i, , drop = FALSE]
  col_i <- row_i$short_column
  x <- feat[[col_i]]
  x_t <- apply_transform(x, row_i$transform)
  z <- safe_z(x_t)
  sgn <- ifelse(is.na(row_i$direction) || row_i$direction >= 0, 1, -1)
  c_i <- z * sgn * row_i$weight
  contrib[[i]] <- c_i
  work[[paste0(col_i, "_zdirw")]] <- c_i
}

score_raw <- Reduce(`+`, contrib) / sum_w
score_z <- safe_z(score_raw)
score_min <- min(score_raw, na.rm = TRUE)
score_max <- max(score_raw, na.rm = TRUE)
score_0_100 <- if (is.finite(score_min) && is.finite(score_max) && score_max > score_min) {
  100 * (score_raw - score_min) / (score_max - score_min)
} else {
  rep(50, length(score_raw))
}
rank_0_100 <- 100 * (rank(score_raw, ties.method = "average") - 1) / (length(score_raw) - 1)

out <- data.frame(
  hex_id = feat$hex_id,
  score_raw = score_raw,
  score_z = score_z,
  score_0_100 = score_0_100,
  score_rank_0_100 = rank_0_100,
  stringsAsFactors = FALSE
)

DBI::dbWriteTable(con, score_id, out, overwrite = TRUE)
DBI::dbExecute(
  con,
  paste0(
    "CREATE INDEX IF NOT EXISTS ",
    score_table,
    "_hex_id_idx ON ",
    DBI::dbQuoteIdentifier(con, score_id),
    "(hex_id);"
  )
)

sql_view <- sprintf(
  paste(
    "CREATE OR REPLACE VIEW %s.%s AS",
    "SELECT g.h3 AS h3_id, g.geometry, s.*",
    "FROM %s.%s g",
    "LEFT JOIN %s.%s s ON g.h3 = s.hex_id;"
  ),
  schema, score_view,
  schema, hex_table,
  schema, score_table
)
DBI::dbExecute(con, sql_view)

n_hex <- DBI::dbGetQuery(con, sprintf("SELECT COUNT(*) AS n FROM %s.%s", schema, hex_table))$n[[1]]
n_out <- DBI::dbGetQuery(con, sprintf("SELECT COUNT(*) AS n FROM %s.%s", schema, score_table))$n[[1]]
if (!isTRUE(n_hex == n_out)) {
  stop(sprintf("Row mismatch: %s.%s=%s vs %s.%s=%s", schema, hex_table, n_hex, schema, score_table, n_out))
}

message("Done.")
message("Score table: ", schema, ".", score_table, " (rows=", n_out, ")")
message("Score view:  ", schema, ".", score_view)
message("Active indicators: ", nrow(cfg))
