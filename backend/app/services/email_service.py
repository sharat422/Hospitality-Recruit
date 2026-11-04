"""
Email service for demo booking notifications
Sends confirmation emails to prospects and notifications to admin team
"""
import os
import logging
from typing import List, Optional
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import asyncio

logger = logging.getLogger(__name__)

# Email configuration
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")
FROM_EMAIL = os.getenv("FROM_EMAIL", "demo@hosprecruit.com")
FROM_NAME = "HospRecruit AI"


def send_email_sync(
    to_email: str,
    subject: str,
    html_content: str,
    plain_text: Optional[str] = None,
) -> bool:
    """Send email synchronously (for background tasks)"""
    try:
        if not all([SMTP_USER, SMTP_PASSWORD]):
            logger.warning("SMTP credentials not configured, skipping email")
            return False
        
        # Create message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{FROM_NAME} <{FROM_EMAIL}>"
        msg["To"] = to_email
        
        # Add plain text part
        if plain_text:
            msg.attach(MIMEText(plain_text, "plain"))
        
        # Add HTML part
        msg.attach(MIMEText(html_content, "html"))
        
        # Send via SMTP
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        
        logger.info(f"Email sent to {to_email} with subject: {subject}")
        return True
    
    except Exception as e:
        logger.error(f"Error sending email to {to_email}: {str(e)}")
        return False


def send_demo_booked_email(
    email: str,
    first_name: str,
    company_name: str,
) -> bool:
    """Send confirmation email to prospect after demo booking"""
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 40px 20px; text-align: center; border-radius: 8px 8px 0 0; }}
            .content {{ background: #f9fafb; padding: 40px 20px; border-radius: 0 0 8px 8px; }}
            .heading {{ color: #1f2937; font-size: 24px; margin-bottom: 20px; }}
            .text {{ color: #4b5563; font-size: 16px; line-height: 1.6; margin-bottom: 16px; }}
            .highlight {{ background: #fffbeb; border-left: 4px solid #f59e0b; padding: 16px; margin: 20px 0; }}
            .cta {{ display: inline-block; background: #667eea; color: white; padding: 12px 32px; text-decoration: none; border-radius: 6px; margin: 20px 0; }}
            .footer {{ color: #6b7280; font-size: 14px; text-align: center; margin-top: 40px; padding-top: 20px; border-top: 1px solid #e5e7eb; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Demo Scheduled! 🎉</h1>
            </div>
            <div class="content">
                <p class="text">Hi {first_name},</p>
                
                <p class="text">
                    Thank you for requesting a demo of HospRecruit AI! We're excited to show you how we can transform your 
                    hospitality hiring process at <strong>{company_name}</strong>.
                </p>
                
                <div class="highlight">
                    <strong>✓ What happens next:</strong>
                    <p class="text" style="margin-top: 10px;">
                        Our team will reach out within 24 hours to confirm your demo time and answer any questions. 
                        You'll get an exclusive look at our AI screening, shift scheduling, and ATS sync features designed 
                        specifically for hospitality teams.
                    </p>
                </div>
                
                <p class="text">
                    <strong>Typical ROI from our customers:</strong><br>
                    • 70% reduction in screening time<br>
                    • 60% faster time-to-hire<br>
                    • 50% fewer no-shows<br>
                    • $1,080+ ROI per hire
                </p>
                
                <p class="text">
                    Questions in the meantime? Reply to this email anytime.
                </p>
                
                <p class="text">
                    Looking forward to connecting!<br>
                    <strong>The HospRecruit AI Team</strong>
                </p>
            </div>
            <div class="footer">
                <p>© 2026 HospRecruit AI. All rights reserved.<br>
                   <a href="https://hosprecruit.com" style="color: #667eea; text-decoration: none;">hosprecruit.com</a>
                </p>
            </div>
        </div>
    </body>
    </html>
    """
    
    plain_text = f"""Hi {first_name},

Thank you for requesting a demo of HospRecruit AI! We're excited to show you how we can transform your 
hospitality hiring process at {company_name}.

WHAT HAPPENS NEXT:
Our team will reach out within 24 hours to confirm your demo time and answer any questions.

TYPICAL ROI FROM OUR CUSTOMERS:
• 70% reduction in screening time
• 60% faster time-to-hire
• 50% fewer no-shows
• $1,080+ ROI per hire

Questions? Reply to this email anytime.

Looking forward to connecting!
The HospRecruit AI Team

---
© 2026 HospRecruit AI. All rights reserved.
hosprecruit.com"""
    
    return send_email_sync(
        to_email=email,
        subject="Your HospRecruit AI Demo is Confirmed! 🎉",
        html_content=html_content,
        plain_text=plain_text,
    )


def send_demo_notification_admin(demo_data: dict) -> bool:
    """Send notification to admin team when new demo request is created"""
    
    if not ADMIN_EMAIL:
        logger.warning("ADMIN_EMAIL not configured, skipping admin notification")
        return False
    
    # Calculate fit score
    hiring_volume_score = {"50+": 30, "10-50": 20, "5-10": 10, "1-5": 5}.get(
        demo_data.get("hiring_volume"), 0
    )
    company_size_score = {"500+": 25, "200-500": 20, "50-200": 10, "1-50": 5}.get(
        demo_data.get("company_size"), 0
    )
    budget_score = {"$5k+": 25, "$2k-$5k": 20, "$500-$2k": 10, "Under $500": 5}.get(
        demo_data.get("budget_range"), 0
    )
    total_score = hiring_volume_score + company_size_score + budget_score
    fit = "🟢 HIGH" if total_score >= 70 else "🟡 MEDIUM" if total_score >= 40 else "🔴 LOW"
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: Arial, sans-serif; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: #667eea; color: white; padding: 20px; border-radius: 4px; }}
            .section {{ margin: 20px 0; }}
            .field {{ margin: 10px 0; }}
            .label {{ font-weight: bold; color: #333; }}
            .value {{ color: #666; margin-left: 10px; }}
            table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
            td {{ padding: 8px; border: 1px solid #ddd; }}
            .fit-badge {{ display: inline-block; padding: 5px 12px; border-radius: 20px; font-weight: bold; }}
            .fit-high {{ background: #d4edda; color: #155724; }}
            .fit-medium {{ background: #fff3cd; color: #856404; }}
            .fit-low {{ background: #f8d7da; color: #721c24; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h2>🎯 New Demo Request</h2>
                <p style="margin: 0; font-size: 14px;">Prospect Fit: <span class="fit-badge fit-{('high' if total_score >= 70 else 'medium' if total_score >= 40 else 'low')}"> {fit} </span></p>
            </div>
            
            <div class="section">
                <h3>Prospect Information</h3>
                <div class="field">
                    <span class="label">Name:</span>
                    <span class="value">{demo_data.get('first_name')} {demo_data.get('last_name')}</span>
                </div>
                <div class="field">
                    <span class="label">Email:</span>
                    <span class="value"><a href="mailto:{demo_data.get('email')}">{demo_data.get('email')}</a></span>
                </div>
                <div class="field">
                    <span class="label">Phone:</span>
                    <span class="value">{demo_data.get('phone', 'Not provided')}</span>
                </div>
                <div class="field">
                    <span class="label">Company:</span>
                    <span class="value">{demo_data.get('company_name')}</span>
                </div>
                <div class="field">
                    <span class="label">Industry:</span>
                    <span class="value">{demo_data.get('industry', 'Not specified')}</span>
                </div>
            </div>
            
            <div class="section">
                <h3>Qualification Details</h3>
                <table>
                    <tr>
                        <td><strong>Hiring Volume</strong></td>
                        <td>{demo_data.get('hiring_volume', 'Not specified')}</td>
                    </tr>
                    <tr>
                        <td><strong>Company Size</strong></td>
                        <td>{demo_data.get('company_size', 'Not specified')}</td>
                    </tr>
                    <tr>
                        <td><strong>Budget</strong></td>
                        <td>{demo_data.get('budget_range', 'Not specified')}</td>
                    </tr>
                    <tr>
                        <td><strong>Demo Type</strong></td>
                        <td>{demo_data.get('demo_type', 'general')}</td>
                    </tr>
                    <tr>
                        <td><strong>Timezone</strong></td>
                        <td>{demo_data.get('timezone', 'Not specified')}</td>
                    </tr>
                </table>
            </div>
            
            <div class="section">
                <h3>Pain Points</h3>
                <p>{', '.join(demo_data.get('current_pain_points', [])) or 'Not specified'}</p>
            </div>
            
            {f'<div class="section"><h3>Additional Notes</h3><p>{demo_data.get("notes", "None")}</p></div>' if demo_data.get('notes') else ''}
            
            <div class="section">
                <p style="font-size: 12px; color: #999;">
                    Request ID: {demo_data.get('id')}<br>
                    Source: {demo_data.get('source', 'unknown')}<br>
                    Created: {datetime.fromisoformat(demo_data.get('created_at')).strftime('%Y-%m-%d %H:%M:%S') if demo_data.get('created_at') else 'Unknown'}
                </p>
            </div>
        </div>
    </body>
    </html>
    """
    
    return send_email_sync(
        to_email=ADMIN_EMAIL,
        subject=f"🎯 New Demo Request - {demo_data.get('company_name')} {fit}",
        html_content=html_content,
    )


def send_demo_scheduled_email(
    email: str,
    first_name: str,
    scheduled_datetime: str,
    demo_link: str,
) -> bool:
    """Send email when demo is actually scheduled"""
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: Arial, sans-serif; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .highlight {{ background: #e0e7ff; border-left: 4px solid #667eea; padding: 20px; margin: 20px 0; }}
            .cta {{ display: inline-block; background: #667eea; color: white; padding: 12px 32px; text-decoration: none; border-radius: 6px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>Your Demo is Scheduled! ✅</h2>
            
            <div class="highlight">
                <strong>📅 Date & Time:</strong><br>
                {scheduled_datetime}
            </div>
            
            <p>Hi {first_name},</p>
            <p>Great news! Your HospRecruit AI demo is confirmed. Here's what to expect:</p>
            
            <ul>
                <li><strong>AI Screening Demo</strong> - See how to auto-screen 100+ applicants in minutes</li>
                <li><strong>Shift Scheduler</strong> - Automate scheduling with calendar sync</li>
                <li><strong>ATS Integration</strong> - Seamless sync with your existing tools</li>
                <li><strong>Custom ROI Analysis</strong> - We'll calculate your specific savings</li>
            </ul>
            
            <p><a href="{demo_link}" class="cta">Join Demo →</a></p>
            
            <p>Can't make it? Let us know and we'll reschedule!</p>
            
            <p>The HospRecruit AI Team</p>
        </div>
    </body>
    </html>
    """
    
    return send_email_sync(
        to_email=email,
        subject="Your Demo is Confirmed! ✅",
        html_content=html_content,
    )
