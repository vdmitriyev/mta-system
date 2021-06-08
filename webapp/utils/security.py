import string
import random
from hashlib import blake2b
from hmac import compare_digest

def random_string(str_length=10):
    ''' Generate a random string of letters and digits '''

    if str_length < 2:
        str_length = 3
    characters = string.ascii_letters + string.digits
    str_all = ''.join(random.choice(characters) for i in range(str_length-2))
    str_digits = ''.join(random.choice(string.digits) for i in range(2))
    return str_all + str_digits

def generate_pin(max_numbers=4):
    ''' Generate PIN number '''

    return str(int(random.random() * pow(10, max_numbers))).zfill(4)

def make_hash(plain_txt, HASH_KEY, AUTH_SIZE = 16):
    ''' Quick and dirty hashing of the given text'''

    h = blake2b(digest_size=AUTH_SIZE, key=HASH_KEY)
    h.update(plain_txt.encode('utf-8'))
    #return h.hexdigest().encode('utf-8')
    return h.hexdigest()#.decode('utf-8')

def verify_hash(plain_txt, hash_txt, HASH_KEY):
    ''' Quick and dirty verification of the given hash and plain text'''

    hash_to_verify = make_hash(plain_txt, HASH_KEY)
    return (str(hash_to_verify) == str(hash_txt))
