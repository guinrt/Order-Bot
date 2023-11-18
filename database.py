import pymongo

# create a connection to the MongoDB
client = pymongo.MongoClient()

# create a database
db = client['']

# create collections within the database
products = db['products']
orders = db['orders']

# create a list of products to insert
products_list = [
    {"id": "1", "name": "", "price": , "stock": },
]

def get_products():
    return list(products.find({}))

def decrement_stock(product: str, quantity: int) -> None:
    # Retrieve the current stock of the selected product
    product_doc = products.find_one({"name": product})
    current_stock = product_doc["stock"]

    # Calculate the new stock after decrementing the quantity
    new_stock = current_stock - quantity

    if new_stock < 0:
        # Stock cannot be negative, handle the insufficient stock scenario
        print("Insufficient stock for", product)

    # Update the stock in the database
    products.update_one({"name": product}, {"$set": {"stock": new_stock}})

def add_order(product: str, quantity: int, option: str, location: str, name: str) -> None:
    order = {
        "product": product,
        "quantity": quantity,
        "option": option,
        "location": location,
        "name": name
    }

    # Insert the order into the "transactions" collection
    orders.insert_one(order)

    # Decrement the stock of the ordered product
    decrement_stock(product, quantity)