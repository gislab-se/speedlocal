# Sol och Vind TODO

## Karta och lager

- Utred kvarvarande vita polygoner i kartan. Nuvarande Leaflet-rendering plattar ut innerringar, men vissa oönskade vita former visas fortfarande och behöver lösas i grundlagret snarare än i denna appversion.
- Bygg ett renare grundlager för landskapsanalysen så att klusterkartan kan visas utan visuella artefakter.
- Ersätt provisorisk solacceptans med ett riktigt separat solacceptanslager när det finns.
- Utveckla klick-urval direkt i kartan för att lägga till och ta bort hex.

## UX och struktur

- Behåll hexurvalet nedtonat tills kartklick-urval finns.
- Fortsätt förbättra klusterfärger och lagerprioritet efter att grundlagret är stabilt.
- Se över popupinnehåll så att det ligger ännu närmare landskapsanalysens handledarkarta.

## Data och logik

- Fortsätt hålla scenarier och år helt dynamiska från DuckDB-strukturen.
- Kontrollera att ny DuckDB från EML kan bytas in utan kodändring.
