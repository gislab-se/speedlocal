suppressPackageStartupMessages({
  library(DBI)
})

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
zscores_table <- Sys.getenv("GEOCONTEXT_ZSCORES_TABLE", "bornholm_r8_geocontext_zscores")

view_features <- Sys.getenv("QGIS_VIEW_FEATURES", "v_bornholm_r8_geocontext_features")
view_zscores <- Sys.getenv("QGIS_VIEW_ZSCORES", "v_bornholm_r8_geocontext_zscores")

con <- connect_pg(cfg_env)
on.exit(DBI::dbDisconnect(con), add = TRUE)

sql_features <- sprintf(
  paste(
    "CREATE OR REPLACE VIEW %s.%s AS",
    "SELECT g.h3 AS h3_id, g.geometry, f.*",
    "FROM %s.%s g",
    "LEFT JOIN %s.%s f ON g.h3 = f.hex_id;"
  ),
  schema, view_features,
  schema, hex_table,
  schema, features_table
)

sql_zscores <- sprintf(
  paste(
    "CREATE OR REPLACE VIEW %s.%s AS",
    "SELECT g.h3 AS h3_id, g.geometry, z.*",
    "FROM %s.%s g",
    "LEFT JOIN %s.%s z ON g.h3 = z.hex_id;"
  ),
  schema, view_zscores,
  schema, hex_table,
  schema, zscores_table
)

DBI::dbExecute(con, sql_features)
DBI::dbExecute(con, sql_zscores)

message("Created/updated views:")
message(" - ", schema, ".", view_features)
message(" - ", schema, ".", view_zscores)
