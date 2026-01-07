import smtplib
import ssl
from email.message import EmailMessage
from dotenv import dotenv_values

class SMPTEmail:
    def __init__(self, *args, **kwargs):
        config = dotenv_values(".env")
        self.SMTP_SERVER = config.get("SMTP_SERVER")
        self.SMTP_PORT = config.get("SMTP_PORT",587)
        self.SMTP_USER = config.get("SMTP_USER")
        self.SMTP_PASS = config.get("SMTP_PASS")

    def sendEmail(self,toemail:str,subj:str,body:str):
        msg = EmailMessage()
        msg["From"] = "assistant@ozoid.com"
        msg["To"] = toemail
        msg["Subject"] = subj
        msg.set_content(body)

        context = ssl.create_default_context()
        if self.SMTP_SERVER and self.SMTP_PORT:
            with smtplib.SMTP(self.SMTP_SERVER, self.SMTP_PORT) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(self.SMTP_USER, self.SMTP_PASS)
                server.send_message(msg)
