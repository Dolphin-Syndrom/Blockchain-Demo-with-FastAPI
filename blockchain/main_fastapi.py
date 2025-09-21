from collections import OrderedDict
import binascii
import hashlib
import json
from time import time
from urllib.parse import urlparse
from uuid import uuid4

import requests
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

from Crypto.Hash import SHA
from Crypto.PublicKey import RSA
from Crypto.Signature import PKCS1_v1_5


MINING_SENDER = "THE BLOCKCHAIN"
MINING_REWARD = 1
MINING_DIFFICULTY = 2


class Blockchain:
    def __init__(self):
        self.transactions = []
        self.chain = []
        self.nodes = set()
        self.node_id = str(uuid4()).replace('-', '')
        self.create_block(0, '00')

    def register_node(self, node_url):
        parsed_url = urlparse(node_url)
        if parsed_url.netloc:
            self.nodes.add(parsed_url.netloc)
        elif parsed_url.path:
            self.nodes.add(parsed_url.path)
        else:
            raise ValueError('Invalid URL')

    def verify_transaction_signature(self, sender_address, signature, transaction):
        public_key = RSA.importKey(binascii.unhexlify(sender_address))
        verifier = PKCS1_v1_5.new(public_key)
        h = SHA.new(str(transaction).encode('utf8'))
        return verifier.verify(h, binascii.unhexlify(signature))

    def submit_transaction(self, sender_address, recipient_address, value, signature):
        transaction = OrderedDict({
            'sender_address': sender_address,
            'recipient_address': recipient_address,
            'value': value,
        })
        if sender_address == MINING_SENDER:
            self.transactions.append(transaction)
            return len(self.chain) + 1
        else:
            transaction_verification = self.verify_transaction_signature(sender_address, signature, transaction)
            if transaction_verification:
                self.transactions.append(transaction)
                return len(self.chain) + 1
            else:
                return False

    def create_block(self, nonce, previous_hash):
        block = {
            'block_number': len(self.chain) + 1,
            'timestamp': time(),
            'transactions': self.transactions,
            'nonce': nonce,
            'previous_hash': previous_hash,
        }
        self.transactions = []
        self.chain.append(block)
        return block

    def hash(self, block):
        block_string = json.dumps(block, sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()

    def proof_of_work(self):
        last_block = self.chain[-1]
        last_hash = self.hash(last_block)
        nonce = 0
        while self.valid_proof(self.transactions, last_hash, nonce) is False:
            nonce += 1
        return nonce

    def valid_proof(self, transactions, last_hash, nonce, difficulty=MINING_DIFFICULTY):
        guess = (str(transactions) + str(last_hash) + str(nonce)).encode()
        guess_hash = hashlib.sha256(guess).hexdigest()
        return guess_hash[:difficulty] == '0' * difficulty

    def valid_chain(self, chain):
        last_block = chain[0]
        current_index = 1
        while current_index < len(chain):
            block = chain[current_index]
            if block['previous_hash'] != self.hash(last_block):
                return False
            transactions = block['transactions'][:-1]
            transaction_elements = ['sender_address', 'recipient_address', 'value']
            transactions = [OrderedDict((k, transaction[k]) for k in transaction_elements) for transaction in transactions]
            if not self.valid_proof(transactions, block['previous_hash'], block['nonce'], MINING_DIFFICULTY):
                return False
            last_block = block
            current_index += 1
        return True

    def resolve_conflicts(self):
        neighbours = self.nodes
        new_chain = None
        max_length = len(self.chain)
        for node in neighbours:
            try:
                response = requests.get('http://' + node + '/chain', timeout=3)
            except Exception:
                continue
            if response.status_code == 200:
                length = response.json()['length']
                chain = response.json()['chain']
                if length > max_length and self.valid_chain(chain):
                    max_length = length
                    new_chain = chain
        if new_chain:
            self.chain = new_chain
            return True
        return False


app = FastAPI()

# CORS to allow the separate client app to call node APIs
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static and templates
app.mount("/static", StaticFiles(directory=str(__file__).rsplit('/', 1)[0] + "/static"), name="static")
templates = Jinja2Templates(directory=str(__file__).rsplit('/', 1)[0] + "/templates")

blockchain = Blockchain()


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/configure", response_class=HTMLResponse)
async def configure(request: Request):
    return templates.TemplateResponse("configure.html", {"request": request})


@app.post("/transactions/new")
async def new_transaction(
    sender_address: str = Form(...),
    recipient_address: str = Form(...),
    amount: str = Form(...),
    signature: str = Form(...),
):
    required = [sender_address, recipient_address, amount, signature]
    if not all(required):
        raise HTTPException(status_code=400, detail="Missing values")

    transaction_result = blockchain.submit_transaction(sender_address, recipient_address, amount, signature)
    if transaction_result is False:
        return JSONResponse({"message": "Invalid Transaction!"}, status_code=406)
    else:
        return JSONResponse({"message": f"Transaction will be added to Block {transaction_result}"}, status_code=201)


@app.get("/transactions/get")
async def get_transactions():
    return {"transactions": blockchain.transactions}


@app.get("/chain")
async def full_chain():
    return {"chain": blockchain.chain, "length": len(blockchain.chain)}


@app.get("/mine")
async def mine():
    last_block = blockchain.chain[-1]
    nonce = blockchain.proof_of_work()
    blockchain.submit_transaction(sender_address=MINING_SENDER, recipient_address=blockchain.node_id, value=MINING_REWARD, signature="")
    previous_hash = blockchain.hash(last_block)
    block = blockchain.create_block(nonce, previous_hash)
    return {
        'message': "New Block Forged",
        'block_number': block['block_number'],
        'transactions': block['transactions'],
        'nonce': block['nonce'],
        'previous_hash': block['previous_hash'],
    }


@app.post("/nodes/register")
async def register_nodes(nodes: str = Form(...)):
    if nodes is None:
        raise HTTPException(status_code=400, detail="Error: Please supply a valid list of nodes")
    for node in nodes.replace(" ", "").split(','):
        if not node:
            continue
        blockchain.register_node(node)
    return {'message': 'New nodes have been added', 'total_nodes': [node for node in blockchain.nodes]}


@app.get("/nodes/resolve")
async def consensus():
    replaced = blockchain.resolve_conflicts()
    if replaced:
        return {'message': 'Our chain was replaced', 'new_chain': blockchain.chain}
    else:
        return {'message': 'Our chain is authoritative', 'chain': blockchain.chain}


@app.get("/nodes/get")
async def get_nodes():
    return {'nodes': list(blockchain.nodes)}


# Optional: root redirect to UI if needed (kept minimal)
