import smtplib
import os
from email.message import EmailMessage
import finnhub

# Get credentials from GitHub environment variables
EMAIL_ADDRESS = os.environ.get('EMAIL_USER')
EMAIL_PASSWORD = os.environ.get('EMAIL_PASS')


msg = EmailMessage()
msg['Subject'] = 'Automated Report Update'
msg['From'] = EMAIL_ADDRESS
msg['To'] = 'khodge1@hotmail.com'
msg.set_content('The latest stock analysis is ready. Check the hosted HTML link.')

with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
    smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
    smtp.send_message(msg)