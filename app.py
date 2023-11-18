import re
import time
import json
import stripe
import logging
import pymongo
import asyncio
import schedule
import requests
import database
import threading
import pyshorteners
from stripe.error import (
    StripeError
)
from typing import (
    List, Dict
)
from stripe import (
    Webhook
)
from http.server import (
    BaseHTTPRequestHandler, 
    HTTPServer
)
from telegram import (
    ReplyKeyboardMarkup, 
    ReplyKeyboardRemove, 
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup,
    LabeledPrice,
    Bot
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    filters,
    PreCheckoutQueryHandler,
)

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Define order telegram bot
ORDER_BOT_KEY = ""
# Define notification telegram bot
NOTIFICATION_BOT_KEY = ""
# Define staff telegram chat channel id for notifications to be sent to
STAFF_CHANNEL_ID = ""
# Define stripe api key
# real stripe.api_key = "" - use the test key for testing purposes below
stripe.api_key = ""

# Define user conversation states
START, PRODUCT, ORDER_QUANTITY, OPTION, PICKUP, DELIVERY_ADDRESS, NAME, CONFIRM, PROCESS_PAYMENT = range(9)

class TelegramBotHandler:
    # Define command handlers
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Send a welcome message when the command /start is issued."""
        user = update.message.from_user
        await update.message.reply_text(text=f"Hello {user.first_name}! Welcome to _____! Type /help for info on how to use me!")
        context.user_data['state'] = START
        return context.user_data.get('state')

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /help command."""
        help_text = """
        \nWelcome to the _____ Bot! Here are the available commands:
        \n/start - Start the bot and get a welcome message
        \n/help - Info on available commands and how to use the bot
        \n/products - View the available products and make a selection
        \n/cancel - Cancel your order process
        """
        await update.message.reply_text(text=help_text)

    async def handle_invalid_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_input = update.message.text

        # Check if the user's input corresponds to a command
        if user_input.startswith("/"):
            await update.message.reply_text(text="Unrecognized command. Please try again or check /help for guidance.")
        else:
            # Get the current state
            current_state = context.user_data.get('state')

            if current_state == NAME and user_input.isalpha():
                # User is in the process of providing their name, ignore invalid input
                pass
            elif current_state == ORDER_QUANTITY and user_input.isdigit():
                # User is in the process of providing order quantity, ignore invalid input
                pass
            elif current_state == DELIVERY_ADDRESS:
                # User is in the process of providing delivery address, ignore invalid input
                pass
            else:
                await update.message.reply_text(text="Invalid input. Please try again or check /help for guidance.")

    async def show_products(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Display the available products to the user."""
        # Retrieve the available products from the database
        product_docs = database.products.find({"stock": {"$gt": 0}})
        products_list = list(product_docs)

        if not products_list:
            await update.message.reply_text(text='No products available.')
            return

        # Create inline keyboard with product buttons
        keyboard = [[InlineKeyboardButton(f"€{product['price']} - {product['name']}", callback_data=product['name'])] for product in products_list]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Send message with product options
        await update.message.reply_text(text='Please select a product:', reply_markup=reply_markup)

        context.user_data['state'] = PRODUCT
        return context.user_data.get('state')
    
    async def order_product(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()

        product = query.data

        # Prompt the user to enter the quantity
        await query.edit_message_text(text=f"How many {product} do you want to order?")
        context.user_data['product'] = product  # Store the selected product for later use

        # Set the state appropriately and return it
        context.user_data['state'] = ORDER_QUANTITY
        return context.user_data.get('state')

    async def enter_quantity(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Process the entered quantity and store the selected product and quantity."""
        quantity_text = update.message.text
        if not quantity_text.isdigit() or int(quantity_text) <= 0:
            await update.message.reply_text(text="Invalid quantity. Please enter a positive number.")
            return ORDER_QUANTITY  # Return to the same state to allow the user to enter a valid quantity

        quantity = int(quantity_text)
        product = context.user_data.get('product')

        # Retrieve the stock for the selected product
        product_doc = database.products.find_one({"name": product})

        if product_doc is None:
            await update.message.reply_text(text="Selected product is not available.")
            return ORDER_QUANTITY  # Return to the same state to allow the user to select a valid product

        stock = product_doc['stock']

        if quantity > stock:
            await update.message.reply_text(text=f"Insufficient stock. Available stock for {product}: {stock}")
            return ORDER_QUANTITY  # Return to the same state to allow the user to enter a valid quantity

        # Store the selected quantity and product
        context.user_data['quantity'] = quantity
        context.user_data['product'] = product

        """Prompt the user to select the delivery option."""
        keyboard = [
            [InlineKeyboardButton("Pickup", callback_data="pickup")],
            [InlineKeyboardButton("Delivery", callback_data="delivery")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(text="Please select an option:", reply_markup=reply_markup)

        context.user_data['state'] = OPTION
        return context.user_data.get('state')

    async def select_delivery_method(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        delivery_method = query.data

        # Store the selected delivery method in context.user_data or perform any desired logic
        context.user_data['delivery_method'] = delivery_method

        if delivery_method == 'pickup':
            # Handle pickup logic
            """Prompt the user to select the delivery option."""
            keyboard = [
                [InlineKeyboardButton("Estoril", callback_data="estoril")],
                [InlineKeyboardButton("Santos-o-Velho", callback_data="santos-o-velho")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text="You have selected Pickup. Choose from the folowing pikcup points:", reply_markup=reply_markup)
            context.user_data['state'] = PICKUP
            return context.user_data.get('state')

        elif delivery_method == 'delivery':
            # Handle delivery logic
            await query.edit_message_text(text="You have selected Delivery. Please be mindful that there is a €2 charge for delivery. Please provide your address for delivery:")
            context.user_data['state'] = DELIVERY_ADDRESS
            return context.user_data.get('state')

    async def select_pickup_point(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        location = query.data

        # Store the selected pickup point in context.user_data or perform any desired logic
        context.user_data['location'] = location
        await query.edit_message_text(text=f"You have selected to pick up your order from {location.upper()}")
        await query.edit_message_text(text=f"Please provide your full name without special characters:")
        context.user_data['state'] = NAME
        return context.user_data.get('state')

    async def provide_delivery_address(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        location = update.message.text
        context.user_data['location'] = location
        await update.message.reply_text(text="Please provide your full name without special characters:")
        context.user_data['state'] = NAME
        return context.user_data.get('state')

    async def provide_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        name = update.message.text
        context.user_data['name'] = name
        await update.message.reply_text(text="Please confirm your order by typing CONFIRM (all caps):")
        context.user_data['state'] = CONFIRM
        return context.user_data.get('state')

    async def confirm_order(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        # Retrieve the captured data
        product = context.user_data['product']
        quantity = context.user_data.get('quantity')
        option = context.user_data.get('delivery_method')
        location = context.user_data.get('location')
        name = context.user_data.get('name')

        # Send confirmation message
        confirmation_message = f"""
        You've ordered {quantity} {product.upper()}(s), choosing the {option.upper()} option at location {location.upper()} in the name of {name.upper()}.
        If this is correct, please type CONFIRM to proceed to payment.
        """
        await update.message.reply_text(text=confirmation_message)

    async def process_payment(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        # Retrieve the selected product from user context
        product = context.user_data.get('product')
        quantity = context.user_data.get('quantity')
        option = context.user_data.get('delivery_method')
        location = context.user_data.get('location')

        # Retrieve the price for the selected product
        product_doc = database.products.find_one({"name": product})
        if product_doc is None:
            return ConversationHandler.END

        extra_fees = 0

        price = product_doc['price']

        # Calculate final price
        final_price = price * quantity

        if option == "delivery":
            final_price += 2
            extra_fees += 2

        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[
                {
                    'price_data': {
                        'currency': 'eur',
                        'product_data': {
                            'name': product,
                        },
                        'unit_amount': int((price + extra_fees) * 100),
                    },
                    'quantity': quantity,
                },
            ],
            mode='payment',
            success_url='https://yourwebsite.com/success',
            cancel_url='https://yourwebsite.com/cancel',
            payment_intent_data={
                'capture_method': 'manual',
                'metadata': {
                    'product': product,
                    'quantity': quantity,
                    'option': context.user_data.get('delivery_method'),
                    'location': context.user_data.get('location'),
                    'name': context.user_data.get('name'),
                },
            },
        )

        # Get the payment URL from the session and shorten it
        payment_url = URLShortener.shorten_url(session.url)

        quote = f"""
        \nYour order of {quantity} {product.upper()}(s) totals to €{round(final_price, 2)}.
        \nYou've chosen {option.upper()} at {location.upper()}.
        \nPlease click the link below to proceed with the payment:\n\n{payment_url}
        """

        await update.message.reply_text(text=quote)
        # await self.send_order_details_to_channel(context)
        return ConversationHandler.END

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        await update.message.reply_text(text="Order canceled.")
        return ConversationHandler.END

class OrderNotificationBot:
    def __init__(self):
        self.bot_token = NOTIFICATION_BOT_KEY
        self.channel_id = STAFF_CHANNEL_ID
        self.orders = database.orders
        self.bot = Bot(token=self.bot_token)
        # Add a logging statement or print statement to indicate the bot has been initialized
        logging.info("OrderNotificationBot initialized")

    async def send_notification(self, order: Dict[str, str]) -> None:
        message = f"New order received:\nProduct: {order['product']}\nQuantity: {order['quantity']}\nOption: {order['option']}\nLocation: {order['location']}\nName: {order['name']}"
        logging.info(message)
        await self.bot.send_message(chat_id=STAFF_CHANNEL_ID, text=message)
        logging.info("Notification sent")

    async def check_for_new_orders(self) -> None:
        try:
            last_processed_order = await self.orders.find_one(sort=[('_id', pymongo.DESCENDING)])
        except TypeError:
            last_processed_order = None

        if last_processed_order is not None:
            query = {'_id': {'$gt': last_processed_order['_id']}}
            new_orders_cursor = self.orders.find(query)
            new_orders = await new_orders_cursor.to_list(length=None)

            for order in new_orders:
                await self.send_notification(order)

        logging.info("Checking for new orders")

    def start_scheduled_task(self) -> None:
        logging.info("Starting scheduled task")
        while True:
            asyncio.run(self.check_for_new_orders())
            time.sleep(20)  # Wait for 20 seconds



class URLShortener:
    def shorten_url(url):
        shortened_url = pyshorteners.Shortener().tinyurl.short(url)
        return shortened_url

class WebhookHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        self.telegram_bot = kwargs.pop('telegram_bot')
        super().__init__(*args, **kwargs)
    
    def _set_response(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()

    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)

        event_type = self.headers.get('Stripe-Event-Type', None)
        signature = self.headers.get('Stripe-Signature', None)
        webhook_secret = 'whsec_3fa56e3e6600c91861d6e4ab6530da03e4b99ee5a9616acd79d1c7f187978123'  # Replace with your webhook secret

        try:
            event = stripe.Webhook.construct_event(post_data, signature, webhook_secret)
            self.handle_event(event)
        except stripe.error.SignatureVerificationError as e:
            # Invalid signature, handle the error as desired
            logging.error("Signature verification failed: %s", e)
            self.send_response(400)
            self.end_headers()
            return

        self._set_response()
        
    def handle_event(self, event):
        logging.error('I\'m handling the event')
        event_type = event['type']

        if event_type == 'checkout.session.completed':
            checkout_session = event['data']['object']
            payment_intent_id = checkout_session['payment_intent']
            
            # Retrieve the payment_intent object
            payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id)
            
            product = payment_intent['metadata']['product']
            quantity = int(payment_intent['metadata']['quantity'])
            option = payment_intent['metadata']['option']
            location = payment_intent['metadata']['location']
            name = payment_intent['metadata']['name']
            
            # Perform desired actions with product and quantity & more; in this case add the order to the database
            database.add_order(product, quantity, option, location, name)

        else:
            logging.error('Unhandled event type: %s', event_type)

def run(server_class, handler_class, port, telegram_bot):
    server_address = ('', port)
    httpd = server_class(server_address, handler_class)
    print(f'Starting webhook server on port {port}...')
    httpd.serve_forever()

def main() -> None:
    # Create an instance of TelegramBotHandler class
    telegram_bot = TelegramBotHandler()

    # Create an instance of OrderNotificationBot class
    notification_bot = OrderNotificationBot()

    # Set up the webhook server
    PORT = 8080  # Specify the desired port
    server = HTTPServer(('localhost', PORT), lambda *args, **kwargs: WebhookHandler(*args, **kwargs, telegram_bot=telegram_bot))
    print(f'Starting webhook server on port {PORT}...')

    # Start the webhook server in a separate thread
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.start()

    # Start the OrderNotificationBot scheduled task in a separate thread
    notification_thread = threading.Thread(target=notification_bot.start_scheduled_task)
    notification_thread.start()

    # Access all products in order to build CallbackQueryHandler for product selection
    product_docs = database.products.find({"stock": {"$gt": 0}})
    products = list(product_docs)

    # Set up the Order Telegram Bot
    application = Application.builder().token(ORDER_BOT_KEY).build()

    # Define the conversation handler
    conversation_handler = ConversationHandler(
    entry_points=[CommandHandler('start', telegram_bot.start)],
    states={
        START: [
            CommandHandler('start', telegram_bot.start),
            CommandHandler('products', telegram_bot.show_products),
            CommandHandler('help', telegram_bot.help_command),
            CommandHandler('cancel', telegram_bot.cancel),
        ],
        PRODUCT: [
            CallbackQueryHandler(telegram_bot.order_product, pattern="^(" + "|".join(product['name'] for product in products) + ")$"),
            CommandHandler('start', telegram_bot.start),
            CommandHandler('products', telegram_bot.show_products),
            CommandHandler('help', telegram_bot.help_command),
            CommandHandler('cancel', telegram_bot.cancel),
        ],
        ORDER_QUANTITY: [
            MessageHandler(filters.TEXT & filters.Regex(r'^\d+$'), telegram_bot.enter_quantity),
            CommandHandler('start', telegram_bot.start),
            CommandHandler('products', telegram_bot.show_products),
            CommandHandler('help', telegram_bot.help_command),
            CommandHandler('cancel', telegram_bot.cancel),
        ],
        OPTION: [
            CallbackQueryHandler(telegram_bot.select_delivery_method, pattern='^(pickup|delivery)$'),
            CommandHandler('start', telegram_bot.start),
            CommandHandler('products', telegram_bot.show_products),
            CommandHandler('help', telegram_bot.help_command),
            CommandHandler('cancel', telegram_bot.cancel),
        ],
        PICKUP: [
            CallbackQueryHandler(telegram_bot.select_pickup_point, pattern='^(estoril|santos-o-velho)$'),
            CommandHandler('start', telegram_bot.start),
            CommandHandler('products', telegram_bot.show_products),
            CommandHandler('help', telegram_bot.help_command),
            CommandHandler('cancel', telegram_bot.cancel),
        ],
        DELIVERY_ADDRESS: [
            MessageHandler(filters.TEXT & filters.Regex(r'^[A-Za-z0-9\s,-]+$'), telegram_bot.provide_delivery_address),
            CommandHandler('start', telegram_bot.start),
            CommandHandler('products', telegram_bot.show_products),
            CommandHandler('help', telegram_bot.help_command),
            CommandHandler('cancel', telegram_bot.cancel),
        ],
        NAME: [
            MessageHandler(filters.TEXT & filters.Regex(r'^[A-Za-z\s-]+$'), telegram_bot.provide_name),
            CommandHandler('start', telegram_bot.start),
            CommandHandler('products', telegram_bot.show_products),
            CommandHandler('help', telegram_bot.help_command),
            CommandHandler('cancel', telegram_bot.cancel),
        ],
        CONFIRM: [
            MessageHandler(filters.TEXT & filters.Regex(re.compile(r'(?i)^confirm$')), telegram_bot.process_payment),
            CommandHandler('start', telegram_bot.start),
            CommandHandler('products', telegram_bot.show_products),
            CommandHandler('help', telegram_bot.help_command),
            CommandHandler('cancel', telegram_bot.cancel),
        ],
    },
    fallbacks=[MessageHandler(filters.TEXT, telegram_bot.handle_invalid_input)]
    )

    # Add the conversation handler to the dispatcher
    application.add_handler(conversation_handler)

    # Start the bot
    asyncio(application.run_polling())

if __name__ == '__main__':
    main()
