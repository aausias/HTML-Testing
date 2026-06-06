# 📊 Dashboard diario de acciones (IBKR + Revolut)

Genera un panel con tus posiciones, **noticias clave** e **insights** ("qué podría
pasar") de cada acción, y te lo envía por **email** + lo publica como **web**.
Pensado para ejecutarse en **rutina automática 1–2 veces al día**.

## ¿Qué hace?

1. Lee tus posiciones de **IBKR** (Flex Web Service, solo lectura) y **Revolut**
   (config o CSV) y las consolida por ticker.
2. Descarga precio, rango 52s, YTD y momentum de cada acción.
3. Baja titulares recientes y los puntúa por sentimiento.
4. Genera insights por reglas (momentum + rango + sentimiento), con opción de
   enriquecerlos con la API de Claude.
5. Renderiza `docs/index.html` (web) y envía el email.

## Estructura

```
config/settings.yaml      # tu portafolio Revolut, watchlist y preferencias
data/holdings_snapshot.json  # respaldo de posiciones IBKR (si no usas Flex aún)
src/                      # pipeline (conectores, datos, noticias, insights, render, email)
docs/index.html           # dashboard generado (GitHub Pages)
.github/workflows/dashboard.yml  # cron 2x/día + ejecución manual
```

## Ejecutar a mano

```bash
pip install -r requirements.txt
python src/main.py
```

Sin secrets configurados funciona igual: usa el snapshot de IBKR de respaldo y
las posiciones de Revolut de `config/settings.yaml`, genera la web y omite el email.

## Automatización (GitHub Actions, 2×/día)

El workflow ya corre de lunes a viernes (pre-apertura y post-cierre US). Para que
sea **totalmente autónomo**, añade estos *Secrets* en
`Settings → Secrets and variables → Actions`:

| Secret | Para qué | Obligatorio |
|---|---|---|
| `IBKR_FLEX_TOKEN` | Posiciones IBKR en vivo (Flex Web Service) | Recomendado |
| `IBKR_FLEX_QUERY_ID` | ID del Flex Query de posiciones | Recomendado |
| `GMAIL_ADDRESS` | Remitente del email | Para email |
| `GMAIL_APP_PASSWORD` | [App Password](https://myaccount.google.com/apppasswords) de Gmail | Para email |
| `ANTHROPIC_API_KEY` | Insights enriquecidos con Claude (opción) | Opcional |

### Conectar IBKR (Flex Web Service, solo lectura)

1. IBKR Client Portal → **Performance & Reports → Flex Queries**.
2. Crea un *Activity Flex Query* que incluya la sección **Open Positions**.
3. Apunta el **Query ID** → secret `IBKR_FLEX_QUERY_ID`.
4. En **Settings → Flex Web Service**, activa y genera el **token** → secret
   `IBKR_FLEX_TOKEN`. Es de **solo lectura** (no permite operar).

> Mientras no configures Flex, el dashboard usa el snapshot de
> `data/holdings_snapshot.json` (capturado el 2026-06-06).

### Revolut

Revolut no tiene API automatizable: mantén tus posiciones en
`config/settings.yaml → revolut_holdings`, o exporta un CSV a
`data/revolut_positions.csv` (ver `data/revolut_positions.example.csv`).

### Publicar la web (GitHub Pages)

`Settings → Pages → Source: Deploy from a branch`, carpeta `/docs`. El workflow
hace commit del `docs/index.html` actualizado en cada ejecución.

### Horario

Edita los `cron` en `.github/workflows/dashboard.yml` (están en **UTC**).
Por defecto: 13:00 UTC (pre-apertura) y 20:15 UTC (post-cierre), L–V.

## Aviso

Información con fines informativos. **No es asesoramiento de inversión.**
