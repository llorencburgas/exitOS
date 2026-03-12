import logging
logger = logging.getLogger("exitOS")

DEVICE_REGISTRY = {}

def register_device(device_type):
    """Decorator to register a device type"""
    def wrapper(cls):
        DEVICE_REGISTRY[device_type] = cls
        return cls
    return wrapper

def get_registered(device_type):
    """Retrieve a device class already registered"""
    return DEVICE_REGISTRY.get(device_type)



def create_device_from_config(config,database):
    """
    Creates a device instance from a config dict.
    Only loads/install the module if the user actually uses it.
    """
    device_type = config['device_type']

    # 1. Si ja està registrat:
    cls = get_registered(device_type)
    if cls:
        return cls(config, database)

    # 2. Si no està registrat, intentem carregar el mòdul dinàmicament
    module_name = f"abstraction.assets.{device_type}"

    try:
        __import__(module_name)
    except Exception as e:
       logger.warning(f"⚠️ Failed to import {module_name}: {e}")

    # 3. Un cop importat, el decorador s'haurà executat, hauria d'existit ja
    cls = get_registered(device_type)
    if not cls:
        logger.error(f"❌ Device {device_type} is not registered")


    return cls(config, database)