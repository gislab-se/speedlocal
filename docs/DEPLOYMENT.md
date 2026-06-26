# Deployment Notes

## Static Page

Target path:

`https://gislab-se.github.io/speedlocal/landskapspotential/`

GitHub Pages is static hosting only. If GitHub Pages cannot publish from the
private repo under the current plan, keep the repo private during development
and make it public temporarily only when publication is needed.

## Interactive App

Run locally:

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py --server.address 127.0.0.1 --server.port 8502
```

Future hosting should use Flowcore, Docker/server runtime, or a compatible
Streamlit app host.

## Runtime Data

Preferred order:

1. Validated Postgres runtime tables.
2. Documented file fallback paths.
3. Planned/disabled region state.

Do not remove file fallbacks until the database-backed path has matching
validation.
