"""Envío del dashboard por email vía SMTP (Gmail App Password).

Secrets necesarios para la rutina headless:
  GMAIL_ADDRESS        -> tu correo (remitente)
  GMAIL_APP_PASSWORD   -> App Password de Google (no tu contraseña normal)
"""
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def send_email(html_body, subject, to_addr):
    sender = os.getenv("GMAIL_ADDRESS")
    password = os.getenv("GMAIL_APP_PASSWORD")
    if not sender or not password:
        print("[emailer] Sin GMAIL_ADDRESS/GMAIL_APP_PASSWORD; se omite el envío.")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to_addr
    msg.attach(MIMEText("Abre este correo en un cliente con HTML.", "plain"))
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender, password)
        server.sendmail(sender, [to_addr], msg.as_string())
    print(f"[emailer] Email enviado a {to_addr}")
    return True
