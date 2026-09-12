"""SMTP transport; never return OTP codes from an HTTP endpoint."""
import smtplib,ssl,socket
from email.message import EmailMessage
class SMTPMailer:
    def __init__(self,settings):self.settings=settings
    def send(self,email,code,purpose):
        s=self.settings
        if not s.smtp_host or not s.smtp_from:
            raise RuntimeError("SMTP_NOT_CONFIGURED")
        msg=EmailMessage()
        msg["From"]=s.smtp_from;msg["To"]=email;msg["Subject"]="Foodiemo 驗證碼"
        msg.set_content("您的"+("註冊" if purpose=="signup" else "重設密碼")+"驗證碼為 "+code+"，10 分鐘內有效。")
        # Windows computer names may contain Chinese; SMTP EHLO requires ASCII.
        hostname=socket.getfqdn().encode("idna").decode("ascii")
        with smtplib.SMTP(s.smtp_host,s.smtp_port,timeout=10,local_hostname=hostname) as server:
            server.ehlo();server.starttls(context=ssl.create_default_context());server.ehlo()
            if s.smtp_user:
                password=s.smtp_password.replace(" ","") if s.smtp_host.lower()=="smtp.gmail.com" else s.smtp_password
                server.login(s.smtp_user,password)
            server.send_message(msg)
class CaptureMailer:
    """Injected by isolated tests, not selectable through public HTTP."""
    def __init__(self):self.messages=[]
    def send(self,email,code,purpose):self.messages.append(dict(email=email,code=code,purpose=purpose))
