# /web_auth/utils/email.py
import boto3, os
from log_helper.logger import get_logger

from config import (
    AWS_ACCESS_KEY_ID,
    AWS_SECRET_ACCESS_KEY,
    AWS_REGION,
    SES_SOURCE
)

logger = get_logger()

ses = boto3.client(
    "ses",
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION,
)

def send_email(email: str, subject: str, plain_text: str, html_body: str | None = None):
    """Generic SES email sender with logging."""
    logger.info(f"📧 Sending email to {email}, subject={subject}, from={SES_SOURCE}")

    if not html_body:
        html_body = plain_text

    try:
        response = ses.send_email(
            Source=SES_SOURCE,
            Destination={"ToAddresses": [email]},
            Message={
                "Subject": {"Data": subject},
                "Body": {
                    "Text": {"Data": plain_text},
                    "Html": {"Data": html_body},
                },
            },
        )
        logger.info(f"✅ SES send_email response: {response}")
        return response
    except Exception as e:
        logger.error(f"❌ SES send_email failed: {e}", exc_info=True)
        raise

def send_temp_password(email: str, temp_password: str):
    """Send the standard temp password email for password-based approvals."""
    subject = "Your BioInsight Account Approved"
    plain_text = (
        f"Your account has been approved.\n\n"
        f"Temporary password: {temp_password}\n\n"
        "Please log in and reset it immediately."
    )
    return send_email(email, subject, plain_text)

def send_admin_notification(
    full_name: str,
    email: str,
    organization: str,
    job_title: str,
    additional_info: str,
    auth_provider: str,
    logo_url: str,
    admin_panel_url: str
):
    """
    Send personalized notification to each admin about new signup request.
    Fetches admin users from DynamoDB and sends personalized emails to each.
    
    Args:
        full_name: User's full name
        email: User's email address
        organization: User's organization
        job_title: User's job title
        additional_info: Additional information provided by user
        auth_provider: "password" or "google"
        logo_url: URL for the logo image
        admin_panel_url: URL for the admin panel
    """
    from .email_renderer import render_email
    from .dynamo import get_admin_users
    import re
    
    # Fetch admin users from database
    admin_users = get_admin_users()
    
    if not admin_users:
        logger.warning(f"No admin users found in database - skipping notification for {email}")
        return
    
    logger.info(f"Notifying {len(admin_users)} admin users about new signup: {email}")
    
    subject = f"BioInsight AI - New Signup Request: {full_name}"
    
    def extract_first_name(full_name_str: str) -> str:
        """
        Extract first name from full name.
        1. If name contains quotes (e.g., 'Ratna "Rajesh" Thangudu'), extract quoted name
        2. Otherwise, return the first word (first name)
        """
        # Try to find name in quotes
        quoted_match = re.search(r'["""](.*?)["""]', full_name_str)
        if quoted_match:
            return quoted_match.group(1)
        
        # Otherwise, get first word (first name)
        first_word = full_name_str.split()[0] if full_name_str.split() else "Admin"
        return first_word
    
    # Send personalized email to each admin
    for admin in admin_users:
        admin_email = admin["user_email"]["S"]
        admin_full_name = admin.get("full_name", {}).get("S", "Admin")
        admin_first_name = extract_first_name(admin_full_name)
        
        try:
            # Plain text version (personalized)
            plain_text = (
                f"Hello {admin_first_name},\n\n"
                f"New signup request received:\n\n"
                f"Name: {full_name}\n"
                f"Email: {email}\n"
                f"Organization: {organization}\n"
                f"Job Title: {job_title}\n"
                f"Additional Info: {additional_info or 'N/A'}\n"
                f"Auth Provider: {auth_provider}\n\n"
                f"Review pending users at: {admin_panel_url}"
            )
            
            # HTML version using template (personalized)
            html_body = render_email(
                "email/admin_new_signup.html",
                subject=subject,
                admin_first_name=admin_first_name,
                full_name=full_name,
                email=email,
                organization=organization,
                job_title=job_title,
                additional_info=additional_info,
                auth_provider=auth_provider,
                admin_panel_url=admin_panel_url,
                logo_url=logo_url,
            )
            
            send_email(admin_email, subject, plain_text, html_body)
            logger.info(f"✅ Admin notification sent to {admin_email} ({admin_first_name})")
        except Exception as e:
            logger.error(f"❌ Failed to send admin notification to {admin_email}: {e}")
