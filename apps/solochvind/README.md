# solochvind

Ny förenklad Streamlit-app för Bornholm med fokus på:

- 3.1 Scenario
- 3.2 Markintensitet
- 3.3.1 Landskaps-acceptans-vind
- 3.3.2 Landskaps-acceptans-sol
- Elmix för bara vind och sol
- Hexurval med manuella tillägg och borttag (`NIMBY`)

Appen läser scenario- och årstruktur direkt från DuckDB och följer därför nya EML-leveranser så länge samma TIMES-tabeller finns i databasen.

Kartvyn bygger på `res9`-hexagonnätet och visar:

- landskapsanalysens klusterlager
- vindacceptanslagret styrt av `3.3.1`
- ett provisoriskt solacceptanslager tills separat sollager finns
- valda och manuellt borttagna hex

Körs via repo-roten genom `app.py`.
