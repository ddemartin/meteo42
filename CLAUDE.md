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

## Accesso da fuori rete

**<https://meteo42.tail1a68b4.ts.net/>** — dentro la tailnet, niente esposto su
Internet. L'indirizzo è quello di un **servizio** Tailscale, non di una
macchina: se il dashboard traslocherà altrove, basterà `tailscale serve drain
svc:meteo42` qui e il comando qui sotto là, e l'indirizzo non cambierà.

```bash
tailscale serve --service=svc:meteo42 --https=443 8501
```

La configurazione di `serve` **non è per sempre**, e va rimessa se l'indirizzo
smette di funzionare. Il CLI non è nel `PATH`: sta in
`/Applications/Tailscale.app/Contents/MacOS/Tailscale`.

Il dashboard ascolta **solo su `127.0.0.1`**: dalla rete di casa in chiaro non
si raggiunge più, si passa dal nome. Per riaprirlo, `--server.address` nel plist
`~/Library/LaunchAgents/com.meteo42.dashboard.plist` (che non sta nel repo).
Dopo averlo modificato non basta `kickstart`, che rilegge la copia in cache:

```bash
launchctl bootout gui/$(id -u)/com.meteo42.dashboard
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.meteo42.dashboard.plist
```

| sintomo | causa | rimedio |
|---|---|---|
| dominio inesistente | il nodo non è host approvato del servizio | vedi `autoApprovers` qui sotto, poi `drain` + `advertise` |
| `502` dal nome del servizio | il servizio c'è, il dashboard no | `launchctl kickstart -k gui/$(id -u)/com.meteo42.dashboard` |
| configurazione sparita | `serve` l'ha persa | rieseguire il comando qui sopra |

`tailscale serve status` che dice `No serve config` **non è un guasto**: i
servizi si vedono solo con `tailscale serve status --json`.

Nella ACL servono due cose distinte, ed è la confusione tra le due che è
costata più tempo in fase di configurazione. Il **grant** decide chi può
raggiungere il servizio — la regola generica `dst: ["*"]` non copre i servizi:

```json
{"src": ["autogroup:member", "tag:brain42-host"],
 "dst": ["svc:meteo42"], "ip": ["tcp:443"]},
```

Gli **autoApprovers** decidono chi può *ospitarlo*. Senza, l'host resta in
attesa di un'approvazione manuale che la console non offre in modo evidente, e
il nome non risolve pur essendo tutto configurato:

```json
"autoApprovers": {
	"services": {
		"svc:meteo42": ["tag:brain42-host"],
	},
},
```

Il demone **non recepisce l'approvazione da solo**
([bug noto](https://github.com/tailscale/tailscale/issues/18821)). Un semplice
`serve advertise` non basta, serve il ciclo completo:

```bash
tailscale serve drain     svc:meteo42
tailscale serve advertise svc:meteo42
```

Lo stato si legge da `CapMap.service-host` in `tailscale status --json`: se
`svc:meteo42` compare lì col suo VIP, l'host è approvato.
