library(DBI)
library(RPostgres)
library(dotenv)


load_pg_env <- function(path = ".env") {
  if (file.exists(path)) {
    dotenv::load_dot_env(path)
  } else {
    stop("❌ .env file not found in project root")
  }
}

connect_pg <- function() {
  load_pg_env()
  
  required <- c("PGDATABASE", "PGUSER", "PGPASSWORD")
  missing <- required[Sys.getenv(required) == ""]
  
  if (length(missing) > 0) {
    stop(
      "❌ Missing environment variables: ",
      paste(missing, collapse = ", ")
    )
  }
  
  DBI::dbConnect(
    RPostgres::Postgres(),
    dbname   = Sys.getenv("PGDATABASE"),
    host     = Sys.getenv("PGHOST", "localhost"),
    port     = as.integer(Sys.getenv("PGPORT", "5432")),
    user     = Sys.getenv("PGUSER"),
    password = Sys.getenv("PGPASSWORD")
  )
}
