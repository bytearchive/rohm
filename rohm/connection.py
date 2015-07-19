from redis import StrictRedis

# conn = Redis()
connection = None


def set_connection_settings(host, port, password):
    global connection
    connection = StrictRedis(host=host, port=port, password=password)


def set_client(redis_client):
    global connection
    connection = redis_client


def get_connection():
    """ Get a connection """
    global connection
    if not connection:
        connection = StrictRedis()

    return connection
