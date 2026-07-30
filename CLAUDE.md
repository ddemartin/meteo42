# meteo42

## Dashboard in produzione

`dashboard.py` gira come servizio launchd (`com.meteo42.dashboard`, porta 8501), non come processo lanciato a mano. Dopo ogni modifica a `dashboard.py` (o altro codice che il servizio importa), va riavviato per caricare la nuova versione:

```bash
launchctl kickstart -k gui/$(id -u)/com.meteo42.dashboard
```

Verifica poi che sia su:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8501
tail -20 logs/dashboard_error.log
```
