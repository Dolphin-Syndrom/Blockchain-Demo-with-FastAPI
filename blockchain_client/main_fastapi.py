from collections import OrderedDict
import binascii

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import Crypto
import Crypto.Random
from Crypto.Hash import SHA
from Crypto.PublicKey import RSA
from Crypto.Signature import PKCS1_v1_5


class Transaction:
    def __init__(self, sender_address, sender_private_key, recipient_address, value):
        self.sender_address = sender_address
        self.sender_private_key = sender_private_key
        self.recipient_address = recipient_address
        self.value = value

    def to_dict(self):
        return OrderedDict({
            'sender_address': self.sender_address,
            'recipient_address': self.recipient_address,
            'value': self.value,
        })

    def sign_transaction(self):
        private_key = RSA.importKey(binascii.unhexlify(self.sender_private_key))
        signer = PKCS1_v1_5.new(private_key)
        h = SHA.new(str(self.to_dict()).encode('utf8'))
        return binascii.hexlify(signer.sign(h)).decode('ascii')


app = FastAPI()

# Static and templates (mirror structure under blockchain_client)
app.mount("/static", StaticFiles(directory=str(__file__).rsplit('/', 1)[0] + "/static"), name="static")
templates = Jinja2Templates(directory=str(__file__).rsplit('/', 1)[0] + "/templates")


@app.get('/', response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse('index.html', {"request": request})


@app.get('/make/transaction', response_class=HTMLResponse)
async def make_transaction(request: Request):
    return templates.TemplateResponse('make_transaction.html', {"request": request})


@app.get('/view/transactions', response_class=HTMLResponse)
async def view_transaction(request: Request):
    return templates.TemplateResponse('view_transactions.html', {"request": request})


@app.get('/wallet/new')
async def new_wallet():
    random_gen = Crypto.Random.new().read
    private_key = RSA.generate(1024, random_gen)
    public_key = private_key.publickey()
    return {
        'private_key': binascii.hexlify(private_key.exportKey(format='DER')).decode('ascii'),
        'public_key': binascii.hexlify(public_key.exportKey(format='DER')).decode('ascii')
    }


@app.post('/generate/transaction')
async def generate_transaction(
    sender_address: str = Form(...),
    sender_private_key: str = Form(...),
    recipient_address: str = Form(...),
    amount: str = Form(...),
):
    transaction = Transaction(sender_address, sender_private_key, recipient_address, amount)
    return { 'transaction': transaction.to_dict(), 'signature': transaction.sign_transaction() }
