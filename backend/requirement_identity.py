"""领域需求身份：SR 可复用，非空 AR 在所有迭代中唯一。"""
def ar_key(value):
    return ''.join(str(value or '').split()).casefold() or None
