from flask import Flask, request, jsonify
from flask_cors import CORS
from serpapi import GoogleSearch
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

app = Flask(__name__)
CORS(app)  # Libera o frontend do GitHub Pages chamar este backend

# ── CONFIGURAÇÕES FIXAS ────────────────────────────────────────
SERPAPI_KEY = "a0bd472c9d10fe8c0bb3bd8e24138ba7e75240b78e367da7357a6c161e272f40"
FROM_EMAIL  = "rufinocosta24@gmail.com"
EMAIL_PASS  = "qkwd iqwi mvyn einu"
# ──────────────────────────────────────────────────────────────


# ══════════════════════════════════════════════════════════════
#  ROTA DE SAÚDE — Render usa isso para saber que o app subiu
# ══════════════════════════════════════════════════════════════
@app.route("/")
def health():
    return jsonify({"status": "ok", "service": "SysVoos API"})


# ══════════════════════════════════════════════════════════════
#  BUSCA VOOS DE IDA
#  POST /api/search
#  Body JSON:
#    origin, destination, outbound_date, return_date,
#    trip_type, stops, currency, sort_by
# ══════════════════════════════════════════════════════════════
@app.route("/api/search", methods=["POST"])
def search_flights():
    body = request.get_json()

    params = {
        "engine":        "google_flights",
        "departure_id":  body.get("origin"),
        "arrival_id":    body.get("destination"),
        "gl":            "br",
        "hl":            "br",
        "currency":      body.get("currency", "BRL"),
        "type":          body.get("trip_type", "1"),
        "outbound_date": body.get("outbound_date"),
        "sort_by":       body.get("sort_by", "2"),
        "stops":         body.get("stops", "2"),
        "api_key":       SERPAPI_KEY,
    }

    # Data de volta só para ida e volta
    if body.get("trip_type") == "1" and body.get("return_date"):
        params["return_date"] = body["return_date"]

    try:
        search  = GoogleSearch(params)
        results = search.get_dict()

        if "error" in results:
            return jsonify({"error": results["error"]}), 400

        flights = list(results.get("best_flights", [])) + \
                  list(results.get("other_flights", []))

        return jsonify({"flights": flights, "total": len(flights)})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ══════════════════════════════════════════════════════════════
#  BUSCA VOOS DE VOLTA (usando departure_token)
#  POST /api/return
#  Body JSON:
#    departure_token, origin, destination,
#    outbound_date, return_date, currency, sort_by
# ══════════════════════════════════════════════════════════════
@app.route("/api/return", methods=["POST"])
def search_return():
    body = request.get_json()

    params = {
        "engine":          "google_flights",
        "departure_id":    body.get("origin"),
        "arrival_id":      body.get("destination"),
        "gl":              "br",
        "hl":              "br",
        "currency":        body.get("currency", "BRL"),
        "type":            "1",
        "outbound_date":   body.get("outbound_date"),
        "return_date":     body.get("return_date"),
        "sort_by":         body.get("sort_by", "2"),
        "departure_token": body.get("departure_token"),
        "api_key":         SERPAPI_KEY,
    }

    try:
        search  = GoogleSearch(params)
        results = search.get_dict()

        if "error" in results:
            return jsonify({"error": results["error"]}), 400

        flights = list(results.get("best_flights", [])) + \
                  list(results.get("other_flights", []))

        return jsonify({"flights": flights, "total": len(flights)})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ══════════════════════════════════════════════════════════════
#  ENVIO DE E-MAIL
#  POST /api/send-email
#  Body JSON:
#    to_emails: [...],
#    subject: "...",
#    outbound_flights: [...],
#    return_flights: [...],
#    selected_outbound: {...} | null
# ══════════════════════════════════════════════════════════════
@app.route("/api/send-email", methods=["POST"])
def send_email():
    body = request.get_json()

    to_emails        = body.get("to_emails", [])
    subject          = body.get("subject", "Resultado de busca de voos")
    outbound_flights = body.get("outbound_flights", [])
    return_flights   = body.get("return_flights", [])
    selected         = body.get("selected_outbound")

    if not to_emails:
        return jsonify({"error": "Nenhum destinatário informado"}), 400

    html = build_email_html(outbound_flights, return_flights, selected)

    try:
        msg = MIMEMultipart()
        msg["From"]    = FROM_EMAIL
        msg["To"]      = ", ".join(to_emails)
        msg["Subject"] = subject
        msg.attach(MIMEText(html, "html"))

        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(FROM_EMAIL, EMAIL_PASS)
        server.sendmail(FROM_EMAIL, to_emails, msg.as_string())
        server.quit()

        return jsonify({"success": True, "sent_to": to_emails})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── HELPER: monta o HTML do e-mail ────────────────────────────
def fmt_duration(minutes):
    if not minutes:
        return "—"
    return f"{minutes // 60}h {minutes % 60}m"


def build_flight_rows(flights, title):
    if not flights:
        return f"<h3 style='color:#d92020'>{title}</h3><p>Nenhum voo encontrado.</p>"

    html = f"<h2 style='color:#d92020;font-family:sans-serif;border-bottom:1px solid #222;padding-bottom:8px'>{title}</h2>"

    for idx, fl in enumerate(flights[:10], 1):
        segs    = fl.get("flights", [])
        first   = segs[0]  if segs else {}
        last    = segs[-1] if segs else {}
        layers  = fl.get("layovers", [])
        price   = fl.get("price")
        dur     = fl.get("total_duration")
        stops   = len(segs) - 1

        dep_name = first.get("departure_airport", {}).get("name", "—")
        dep_id   = first.get("departure_airport", {}).get("id",   "—")
        dep_time = first.get("departure_airport", {}).get("time", "—")
        arr_name = last.get("arrival_airport",  {}).get("name", "—")
        arr_id   = last.get("arrival_airport",  {}).get("id",   "—")
        arr_time = last.get("arrival_airport",  {}).get("time", "—")

        stops_label = "Direto" if stops == 0 else f"{stops} parada(s)"

        html += f"""
        <table width="100%" cellpadding="0" cellspacing="0"
               style="background:#111;border:1px solid #222;border-radius:10px;
                      margin-bottom:14px;font-family:sans-serif;font-size:14px;color:#eee">
          <tr>
            <td style="padding:14px 18px">
              <strong style="color:#d92020;font-size:16px">#{idx} — {first.get('airline','—')} {first.get('flight_number','')}</strong>
              &nbsp;&nbsp;<span style="color:#888;font-size:12px">{stops_label} · {fmt_duration(dur)}</span>
              {"&nbsp;&nbsp;<strong style='color:#27ae60'>R$ " + str(price) + "</strong>" if price else ""}
            </td>
          </tr>
          <tr>
            <td style="padding:0 18px 14px">
              <table width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td style="width:45%;padding:8px 12px;background:#1a1a1a;border-radius:8px">
                    <div style="font-size:11px;color:#555;text-transform:uppercase;letter-spacing:1px">Partida</div>
                    <div style="font-weight:600;margin-top:3px">{dep_name} ({dep_id})</div>
                    <div style="color:#888;font-size:12px;margin-top:2px">{dep_time}</div>
                  </td>
                  <td style="width:10%;text-align:center;color:#d92020;font-size:18px">→</td>
                  <td style="width:45%;padding:8px 12px;background:#1a1a1a;border-radius:8px">
                    <div style="font-size:11px;color:#555;text-transform:uppercase;letter-spacing:1px">Chegada</div>
                    <div style="font-weight:600;margin-top:3px">{arr_name} ({arr_id})</div>
                    <div style="color:#888;font-size:12px;margin-top:2px">{arr_time}</div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
        """

        # Escalas
        for lay in layers:
            html += f"""
          <tr>
            <td style="padding:0 18px 10px">
              <span style="background:#1a1a1a;border:1px solid #333;border-radius:999px;
                           padding:4px 14px;font-size:12px;color:#888">
                ⏱ Escala: {lay.get('name','—')} ({lay.get('id','—')}) — {fmt_duration(lay.get('duration'))}
              </span>
            </td>
          </tr>
            """

        html += "</table>"

    return html


def build_email_html(outbound, ret, selected):
    selected_html = ""
    if selected:
        selected_html = f"""
        <div style="background:#0d1f0d;border:1px solid #27ae60;border-radius:10px;
                    padding:14px 18px;margin-bottom:24px;font-family:sans-serif;color:#eee">
          <strong style="color:#27ae60">✓ Voo de ida selecionado:</strong>
          {selected.get('airline','—')} {selected.get('flight_number','')} —
          {selected.get('departure',{}).get('name','—')} → {selected.get('arrival',{}).get('name','—')}
          {"— R$ " + str(selected['price']) if selected.get('price') else ""}
        </div>
        """

    return f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head><meta charset="UTF-8"/></head>
    <body style="background:#070707;margin:0;padding:24px">
      <div style="max-width:680px;margin:0 auto">

        <div style="text-align:center;margin-bottom:32px">
          <h1 style="font-family:sans-serif;color:#d92020;letter-spacing:4px;margin:0">SYSVOOS</h1>
          <p style="color:#505050;font-family:sans-serif;font-size:13px;margin-top:6px">
            SysTech Tecnologia — Resultado da busca
          </p>
        </div>

        {selected_html}
        {build_flight_rows(outbound, "✈ Voos de Ida")}
        {"" if not ret else build_flight_rows(ret, "↩ Voos de Volta")}

        <p style="text-align:center;color:#333;font-family:sans-serif;
                  font-size:11px;margin-top:32px">
          Gerado automaticamente pelo SysVoos · SysTech Tecnologia
        </p>
      </div>
    </body>
    </html>
    """


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
