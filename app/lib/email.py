"""
Email utility for sending transactional emails.
Uses SMTP for sending order confirmations and other notifications.
"""
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import List, Dict

logger = logging.getLogger("uvicorn")


def send_order_confirmation_email(
    to_email: str,
    customer_name: str,
    order_id: int,
    total_amount: int,
    item_count: int,
    order_items: List[Dict],
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    from_email: str
):
    """
    Send order confirmation email to customer.
    
    Args:
        to_email: Customer's email address
        customer_name: Customer's name
        order_id: Order ID
        total_amount: Total order amount in cents
        item_count: Number of items in order
        order_items: List of dicts with product details (name, quantity, price)
        smtp_host: SMTP server host
        smtp_port: SMTP server port
        smtp_user: SMTP username
        smtp_password: SMTP password
        from_email: Sender email address
    """
    try:
        # Create message
        message = MIMEMultipart("alternative")
        message["Subject"] = f"Order Confirmation - #{order_id}"
        message["From"] = from_email
        message["To"] = to_email

        # Create HTML email body
        html_body = create_order_email_html(
            customer_name=customer_name,
            order_id=order_id,
            total_amount=total_amount,
            item_count=item_count,
            order_items=order_items
        )

        # Create plain text version
        text_body = create_order_email_text(
            customer_name=customer_name,
            order_id=order_id,
            total_amount=total_amount,
            item_count=item_count,
            order_items=order_items
        )

        # Attach both versions
        part1 = MIMEText(text_body, "plain")
        part2 = MIMEText(html_body, "html")
        message.attach(part1)
        message.attach(part2)

        # Send email
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(message)

        logger.info(f"Order confirmation email sent to {to_email} for order #{order_id}")

    except Exception as e:
        # Log error but don't raise - we don't want to fail the order if email fails
        logger.error(f"Failed to send order confirmation email to {to_email}: {str(e)}")


def create_order_email_html(
    customer_name: str,
    order_id: int,
    total_amount: int,
    item_count: int,
    order_items: List[Dict]
) -> str:
    """Create HTML email body for order confirmation."""
    
    # Format amount (assuming cents)
    formatted_amount = f"${total_amount / 100:.2f}"
    
    # Build order items HTML
    items_html = ""
    for item in order_items:
        item_name = item.get("name", "Unknown Product")
        item_quantity = item.get("quantity", 1)
        item_price = item.get("price", 0)
        item_total = item_price * item_quantity
        formatted_item_price = f"${item_price / 100:.2f}"
        formatted_item_total = f"${item_total / 100:.2f}"
        
        items_html += f"""
            <tr>
                <td style="padding: 10px; border-bottom: 1px solid #eee;">{item_name}</td>
                <td style="padding: 10px; border-bottom: 1px solid #eee; text-align: center;">{item_quantity}</td>
                <td style="padding: 10px; border-bottom: 1px solid #eee; text-align: right;">{formatted_item_price}</td>
                <td style="padding: 10px; border-bottom: 1px solid #eee; text-align: right;">{formatted_item_total}</td>
            </tr>
        """
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background-color: #f8f9fa; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
            <h1 style="color: #2c3e50; margin: 0;">Order Confirmation</h1>
            <p style="color: #7f8c8d; margin: 5px 0 0 0;">Order #{order_id}</p>
        </div>
        
        <div style="margin-bottom: 30px;">
            <p>Hi {customer_name},</p>
            <p>Thank you for your order! We're excited to confirm that we've received your order and it's being processed.</p>
        </div>
        
        <div style="background-color: #ffffff; border: 1px solid #dee2e6; border-radius: 8px; padding: 20px; margin-bottom: 20px;">
            <h2 style="color: #2c3e50; margin-top: 0;">Order Summary</h2>
            
            <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
                <thead>
                    <tr style="background-color: #f8f9fa;">
                        <th style="padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6;">Product</th>
                        <th style="padding: 10px; text-align: center; border-bottom: 2px solid #dee2e6;">Qty</th>
                        <th style="padding: 10px; text-align: right; border-bottom: 2px solid #dee2e6;">Price</th>
                        <th style="padding: 10px; text-align: right; border-bottom: 2px solid #dee2e6;">Total</th>
                    </tr>
                </thead>
                <tbody>
                    {items_html}
                </tbody>
            </table>
            
            <div style="text-align: right; padding-top: 15px; border-top: 2px solid #2c3e50;">
                <p style="margin: 5px 0;"><strong>Total Items:</strong> {item_count}</p>
                <p style="margin: 5px 0; font-size: 1.2em;"><strong>Total Amount:</strong> <span style="color: #28a745;">{formatted_amount}</span></p>
            </div>
        </div>
        
        <div style="background-color: #e7f3ff; padding: 15px; border-radius: 8px; margin-bottom: 20px;">
            <p style="margin: 0;"><strong>What's next?</strong></p>
            <p style="margin: 10px 0 0 0;">We'll send you another email with tracking information once your order ships.</p>
        </div>
        
        <div style="color: #7f8c8d; font-size: 0.9em; text-align: center; padding-top: 20px; border-top: 1px solid #dee2e6;">
            <p>If you have any questions, please don't hesitate to contact us.</p>
            <p style="margin: 5px 0;">Thank you for shopping with us!</p>
        </div>
    </body>
    </html>
    """
    
    return html


def create_order_email_text(
    customer_name: str,
    order_id: int,
    total_amount: int,
    item_count: int,
    order_items: List[Dict]
) -> str:
    """Create plain text email body for order confirmation."""
    
    # Format amount
    formatted_amount = f"${total_amount / 100:.2f}"
    
    # Build order items text
    items_text = ""
    for item in order_items:
        item_name = item.get("name", "Unknown Product")
        item_quantity = item.get("quantity", 1)
        item_price = item.get("price", 0)
        item_total = item_price * item_quantity
        formatted_item_total = f"${item_total / 100:.2f}"
        
        items_text += f"  - {item_name} x{item_quantity} = {formatted_item_total}\n"
    
    text = f"""
ORDER CONFIRMATION
Order #{order_id}

Hi {customer_name},

Thank you for your order! We're excited to confirm that we've received your order and it's being processed.

ORDER SUMMARY
{items_text}
-----------------------------------
Total Items: {item_count}
Total Amount: {formatted_amount}

WHAT'S NEXT?
We'll send you another email with tracking information once your order ships.

If you have any questions, please don't hesitate to contact us.

Thank you for shopping with us!
    """
    
    return text.strip()
