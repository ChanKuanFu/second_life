"""SecondLife Flask API using the current ERD only (SQLite development build)."""
import hashlib,hmac,os,secrets,sqlite3,uuid
from datetime import datetime,timedelta,timezone
from functools import wraps
from pathlib import Path
from flask import Flask,g,jsonify,request,send_from_directory
from flask_cors import CORS

ROOT=Path(__file__).resolve().parents[1]
DB_PATH=os.getenv('DATABASE_PATH',str(ROOT/'secondlife_current_erd.db'))
app=Flask(__name__,static_folder=str(ROOT/'frontend'),static_url_path='');CORS(app);TOKENS={}
SCHEMA="""
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS Users(user_id TEXT PRIMARY KEY,name TEXT NOT NULL CHECK(length(name)<=120),email TEXT NOT NULL UNIQUE CHECK(email=lower(email)),password_hash TEXT NOT NULL,role TEXT NOT NULL CHECK(role IN('BUYER','SELLER','ADMIN')),account_status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK(account_status IN('ACTIVE','DEACTIVATED')),created_at TEXT NOT NULL,reputation_score REAL CHECK(reputation_score BETWEEN 1 AND 5),review_count INTEGER NOT NULL DEFAULT 0,is_trusted_seller INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS Categories(category_id TEXT PRIMARY KEY,category_name TEXT NOT NULL UNIQUE CHECK(length(category_name)<=100));
CREATE TABLE IF NOT EXISTS ProductModels(model_id TEXT PRIMARY KEY,category_id TEXT NOT NULL REFERENCES Categories(category_id),model_name TEXT NOT NULL CHECK(length(model_name)<=150),brand TEXT NOT NULL CHECK(length(brand)<=100),item_type TEXT NOT NULL CHECK(length(item_type)<=100),model_description TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS Products(product_id TEXT PRIMARY KEY,model_id TEXT NOT NULL REFERENCES ProductModels(model_id),seller_id TEXT NOT NULL REFERENCES Users(user_id),price REAL NOT NULL CHECK(price>0),condition TEXT NOT NULL CHECK(length(condition)<=50),appearance_note TEXT NOT NULL,minimum_offer_price REAL CHECK(minimum_offer_price>0 AND minimum_offer_price<=price),on_hand_qty INTEGER NOT NULL CHECK(on_hand_qty>=0),reserved_qty INTEGER NOT NULL DEFAULT 0 CHECK(reserved_qty>=0 AND reserved_qty<=on_hand_qty),listing_enabled INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS Addresses(address_id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES Users(user_id),recipient_name TEXT NOT NULL CHECK(length(recipient_name)<=120),phone_number TEXT NOT NULL CHECK(length(phone_number)<=30),address_line TEXT NOT NULL CHECK(length(address_line)<=255),city TEXT NOT NULL CHECK(length(city)<=100),postcode TEXT NOT NULL CHECK(length(postcode)<=20),state TEXT NOT NULL CHECK(length(state)<=100),country TEXT NOT NULL CHECK(length(country)<=100),is_default INTEGER NOT NULL DEFAULT 0);
CREATE UNIQUE INDEX IF NOT EXISTS one_default_address ON Addresses(user_id) WHERE is_default=1;
CREATE TABLE IF NOT EXISTS Cart(cart_id TEXT PRIMARY KEY,user_id TEXT NOT NULL UNIQUE REFERENCES Users(user_id));
CREATE TABLE IF NOT EXISTS Offers(offer_id TEXT PRIMARY KEY,product_id TEXT REFERENCES Products(product_id),buyer_id TEXT NOT NULL REFERENCES Users(user_id),offer_price REAL NOT NULL CHECK(offer_price>0),offer_status TEXT NOT NULL DEFAULT 'PENDING' CHECK(offer_status IN('PENDING','ACCEPTED','REJECTED','WITHDRAWN','EXPIRED')),created_at TEXT NOT NULL,expires_at TEXT NOT NULL CHECK(expires_at>created_at),decided_at TEXT);
CREATE TABLE IF NOT EXISTS Orders(order_id TEXT PRIMARY KEY,buyer_id TEXT NOT NULL REFERENCES Users(user_id),seller_id TEXT NOT NULL REFERENCES Users(user_id),address_id TEXT REFERENCES Addresses(address_id),order_status TEXT NOT NULL DEFAULT 'PENDING' CHECK(order_status IN('PENDING','PAID','CANCELLED','COMPLETED')),created_at TEXT NOT NULL,expires_at TEXT NOT NULL CHECK(expires_at>created_at),cancellation_reason TEXT,recipient_name_snapshot TEXT NOT NULL,phone_snapshot TEXT NOT NULL,address_line_snapshot TEXT NOT NULL,city_snapshot TEXT NOT NULL,postcode_snapshot TEXT NOT NULL,state_snapshot TEXT NOT NULL,country_snapshot TEXT NOT NULL,CHECK(buyer_id<>seller_id));
CREATE TABLE IF NOT EXISTS CartItems(cart_item_id TEXT PRIMARY KEY,cart_id TEXT NOT NULL REFERENCES Cart(cart_id) ON DELETE CASCADE,product_id TEXT REFERENCES Products(product_id),quantity INTEGER NOT NULL DEFAULT 1 CHECK(quantity>0),item_status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK(item_status IN('ACTIVE','SAVED_FOR_LATER')),line_revision TEXT NOT NULL UNIQUE,UNIQUE(cart_id,product_id));
CREATE TABLE IF NOT EXISTS OrderItems(order_item_id TEXT PRIMARY KEY,order_id TEXT REFERENCES Orders(order_id),product_id TEXT REFERENCES Products(product_id),quantity INTEGER NOT NULL DEFAULT 1 CHECK(quantity>0),unit_price_snapshot REAL NOT NULL CHECK(unit_price_snapshot>0),source_cart_line_revision TEXT NOT NULL,UNIQUE(order_id,product_id));
CREATE TABLE IF NOT EXISTS OfferRedemptions(order_item_id TEXT PRIMARY KEY REFERENCES OrderItems(order_item_id),offer_id TEXT NOT NULL UNIQUE REFERENCES Offers(offer_id));
CREATE TABLE IF NOT EXISTS Payments(payment_id TEXT PRIMARY KEY,order_id TEXT UNIQUE REFERENCES Orders(order_id),amount REAL CHECK(amount>0),payment_method TEXT,payment_status TEXT NOT NULL DEFAULT 'PENDING' CHECK(payment_status IN('PENDING','PAID','FAILED')),paid_at TEXT,refund_status TEXT NOT NULL DEFAULT 'NONE' CHECK(refund_status IN('NONE','PENDING','APPROVED','REFUNDED','REJECTED')),refund_amount REAL CHECK(refund_amount>0 AND refund_amount<=amount),refund_reason TEXT,refunded_at TEXT);
CREATE TABLE IF NOT EXISTS Deliveries(delivery_id TEXT PRIMARY KEY,order_id TEXT UNIQUE REFERENCES Orders(order_id),tracking_number TEXT,courier_name TEXT,delivery_status TEXT NOT NULL DEFAULT 'PENDING' CHECK(delivery_status IN('PENDING','SHIPPED','IN_TRANSIT','DELIVERED')),shipped_at TEXT,delivered_at TEXT,receipt_confirmed_at TEXT);
CREATE TABLE IF NOT EXISTS TrackingEvents(event_id TEXT PRIMARY KEY,delivery_id TEXT NOT NULL REFERENCES Deliveries(delivery_id),event_type TEXT NOT NULL CHECK(event_type IN('TRACKING_NUMBER_RECORDED','SHIPPED','IN_TRANSIT','DELIVERED','RECEIPT_CONFIRMED')),event_time TEXT NOT NULL,source TEXT NOT NULL CHECK(source IN('SELLER','TRACKING_SERVICE','BUYER')),UNIQUE(delivery_id,event_type));
CREATE INDEX IF NOT EXISTS tracking_events_delivery ON TrackingEvents(delivery_id);
CREATE TABLE IF NOT EXISTS Notifications(notification_id TEXT PRIMARY KEY,recipient_id TEXT NOT NULL REFERENCES Users(user_id),event_key TEXT NOT NULL,message TEXT NOT NULL,created_at TEXT NOT NULL,read_at TEXT,UNIQUE(recipient_id,event_key));
CREATE TABLE IF NOT EXISTS ReportsDisputes(case_id TEXT PRIMARY KEY,order_id TEXT REFERENCES Orders(order_id),reporter_id TEXT NOT NULL REFERENCES Users(user_id),reported_user_id TEXT REFERENCES Users(user_id),product_id TEXT REFERENCES Products(product_id),case_type TEXT NOT NULL CHECK(case_type IN('USER_REPORT','PRODUCT_REPORT','ORDER_DISPUTE')),description TEXT NOT NULL,case_status TEXT NOT NULL DEFAULT 'PENDING' CHECK(case_status IN('PENDING','RESOLVED','WITHDRAWN')),resolved_by TEXT REFERENCES Users(user_id),resolution_note TEXT,created_at TEXT NOT NULL,resolved_at TEXT,CHECK((case_type='USER_REPORT' AND reported_user_id IS NOT NULL AND product_id IS NULL AND order_id IS NULL) OR(case_type='PRODUCT_REPORT' AND product_id IS NOT NULL AND reported_user_id IS NULL AND order_id IS NULL) OR(case_type='ORDER_DISPUTE' AND order_id IS NOT NULL AND reported_user_id IS NULL AND product_id IS NULL)));
CREATE TABLE IF NOT EXISTS Reviews(review_id TEXT PRIMARY KEY,order_id TEXT REFERENCES Orders(order_id),reviewer_id TEXT NOT NULL REFERENCES Users(user_id),rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),comment TEXT,created_at TEXT NOT NULL,removed_at TEXT,UNIQUE(order_id,reviewer_id));
CREATE TABLE IF NOT EXISTS Wishlist(wishlist_id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES Users(user_id),product_id TEXT REFERENCES Products(product_id),note TEXT,created_at TEXT NOT NULL,UNIQUE(user_id,product_id));
"""
def uid():return str(uuid.uuid4())
def now():return datetime.now(timezone.utc).isoformat()
def label(v):return str(v).replace('_',' ').title()
def db():
 if 'db' not in g:g.db=sqlite3.connect(DB_PATH);g.db.row_factory=sqlite3.Row;g.db.execute('PRAGMA foreign_keys=ON')
 return g.db
@app.teardown_appcontext
def close_db(_):
 c=g.pop('db',None)
 if c:c.close()
def hp(p,s=None):
 s=s or secrets.token_bytes(16);return s.hex()+':'+hashlib.pbkdf2_hmac('sha256',p.encode(),s,160000).hex()
def cp(p,v):
 s,h=v.split(':',1);return hmac.compare_digest(hashlib.pbkdf2_hmac('sha256',p.encode(),bytes.fromhex(s),160000).hex(),h)
def user_out(r):
 d=dict(r);d.update(id=d['user_id'],status=label(d['account_status']),reputation=d['reputation_score'] or 0);return d
def user():
 t=request.headers.get('Authorization','')[7:];s=TOKENS.get(t)
 return db().execute("SELECT * FROM Users WHERE user_id=? AND account_status='ACTIVE'",(s['id'],)).fetchone() if s and s['exp']>datetime.now(timezone.utc) else None
def auth(roles=None):
 def deco(fn):
  @wraps(fn)
  def w(*a,**k):
   g.user=user()
   if not g.user:return jsonify(error='Please sign in first'),401
   if roles and g.user['role'] not in roles:return jsonify(error='Permission denied'),403
   return fn(*a,**k)
  return w
 return deco
def cart(uid_):
 r=db().execute('SELECT cart_id FROM Cart WHERE user_id=?',(uid_,)).fetchone()
 if r:return r['cart_id']
 x=uid();db().execute('INSERT INTO Cart VALUES(?,?)',(x,uid_));return x
def product(pid,only=False):
 r=db().execute('''SELECT p.*,m.model_name,m.brand,m.item_type,m.model_description,c.category_name,u.name seller_name,u.reputation_score seller_reputation,u.review_count,u.is_trusted_seller FROM Products p JOIN ProductModels m ON m.model_id=p.model_id JOIN Categories c ON c.category_id=m.category_id JOIN Users u ON u.user_id=p.seller_id WHERE p.product_id=?''',(pid,)).fetchone()
 return r if r and(not only or(r['listing_enabled'] and r['on_hand_qty']>r['reserved_qty'])) else None
def product_out(r):
 d=dict(r);d.update(id=d['product_id'],title=d['model_name'],description=d['model_description'],min_price=d['minimum_offer_price'] or 0,quantity=d['on_hand_qty']-d['reserved_qty'],status='Available' if d['listing_enabled'] and d['on_hand_qty']>d['reserved_qty'] else 'Unavailable',image_url='');return d
def notify(who,key,msg):db().execute('INSERT OR IGNORE INTO Notifications VALUES(?,?,?,?,?,NULL)',(uid(),who,key,msg,now()))
def event(delivery_id,typ,source='TRACKING_SERVICE'):
 db().execute('INSERT OR IGNORE INTO TrackingEvents VALUES(?,?,?,?,?)',(uid(),delivery_id,typ,now(),source))
def init():
 Path(DB_PATH).parent.mkdir(parents=True,exist_ok=True)
 with sqlite3.connect(DB_PATH) as c:
  c.executescript(SCHEMA)
  if c.execute('SELECT COUNT(*) FROM Users').fetchone()[0]:return
  t=now();ids={}
  for n,e,p,r in [('Aina Tan','aina@example.com','demo123','BUYER'),('Jason Lee','jason@example.com','demo123','SELLER'),('SecondLife Admin','admin@example.com','admin123','ADMIN')]:
   x=uid();ids[e]=x;c.execute('INSERT INTO Users(user_id,name,email,password_hash,role,created_at) VALUES(?,?,?,?,?,?)',(x,n,e,hp(p),r,t))
  cats={}
  for n in ['Electronics','Home','Books','Fashion','Sports']:
   x=uid();cats[n]=x;c.execute('INSERT INTO Categories VALUES(?,?)',(x,n))
  for cat,name,brand,kind,desc,price,floor,cond in [('Electronics','Wireless headphones','SoundPlus','Headphones','Lightly used, excellent battery life.',85,40,'Good'),('Books','Design books bundle','Various','Books','Three design books in very good condition.',32,18,'Very good'),('Home','Desk lamp','Luma','Lighting','Warm LED lamp, includes USB cable.',24,12,'Good'),('Fashion','Canvas tote bag','Local','Bag','Durable everyday tote.',12,5,'Like new')]:
   m,p=uid(),uid();c.execute('INSERT INTO ProductModels VALUES(?,?,?,?,?,?,?)',(m,cats[cat],name,brand,kind,desc,t));c.execute('INSERT INTO Products VALUES(?,?,?,?,?,?,?,?,?,?,?)',(p,m,ids['jason@example.com'],price,cond,desc,floor,1,0,1,t))
@app.before_request
def expiry():
 if request.path.startswith('/api/'):
  db().execute("UPDATE Offers SET offer_status='EXPIRED',decided_at=? WHERE offer_status='PENDING' AND expires_at<=?",(now(),now()));db().commit()
@app.get('/api/health')
def health():return {'ok':True,'service':'SecondLife API'}
@app.post('/api/auth/register')
def register():
 d=request.get_json(silent=True)or{};n=str(d.get('name','')).strip();e=str(d.get('email','')).strip().lower();p=str(d.get('password',''));role=str(d.get('role','BUYER')).upper()
 if not n or '@' not in e or len(p)<6:return jsonify(error='Enter a name, valid email, and password with at least 6 characters'),400
 if role not in ('BUYER','SELLER'):role='BUYER'
 try:x=uid();db().execute('INSERT INTO Users(user_id,name,email,password_hash,role,created_at) VALUES(?,?,?,?,?,?)',(x,n,e,hp(p),role,now()));cart(x);db().commit()
 except sqlite3.IntegrityError:return jsonify(error='Email already registered'),409
 return login_user(x),201
@app.post('/api/auth/login')
def login():
 d=request.get_json(silent=True)or{};r=db().execute('SELECT * FROM Users WHERE email=?',(str(d.get('email','')).lower(),)).fetchone()
 if not r or not cp(str(d.get('password','')),r['password_hash']) or r['account_status']!='ACTIVE':return jsonify(error='Email or password is incorrect'),401
 return login_user(r['user_id'])
def login_user(x):
 t=secrets.token_urlsafe(36);TOKENS[t]={'id':x,'exp':datetime.now(timezone.utc)+timedelta(days=14)};return jsonify(token=t,user=user_out(db().execute('SELECT * FROM Users WHERE user_id=?',(x,)).fetchone()))
@app.post('/api/auth/logout')
@auth()
def logout():TOKENS.pop(request.headers.get('Authorization','')[7:],None);return {'ok':True}
@app.get('/api/me')
@auth()
def me():return jsonify(user_out(g.user))
@app.patch('/api/me')
@auth()
def me_patch():
 d=request.get_json(silent=True)or{};n=str(d.get('name',g.user['name'])).strip();e=str(d.get('email',g.user['email'])).strip().lower()
 if not n or '@' not in e:return jsonify(error='Enter a valid name and email'),400
 try:db().execute('UPDATE Users SET name=?,email=? WHERE user_id=?',(n,e,g.user['user_id']));db().commit()
 except sqlite3.IntegrityError:return jsonify(error='That email is already in use'),409
 return me()
@app.delete('/api/me')
@auth()
def me_delete():db().execute("UPDATE Users SET account_status='DEACTIVATED' WHERE user_id=?",(g.user['user_id'],));db().commit();return {'status':'DEACTIVATED'}
@app.get('/api/categories')
def categories():return jsonify([dict(x)|{'id':x['category_id'],'name':x['category_name']} for x in db().execute('SELECT * FROM Categories ORDER BY category_name')])
@app.route('/api/admin/categories',methods=['POST'])
@auth({'ADMIN'})
def cat_add():
 n=str((request.get_json(silent=True)or{}).get('name','')).strip();x=uid()
 try:db().execute('INSERT INTO Categories VALUES(?,?)',(x,n));db().commit();return {'id':x,'name':n},201
 except sqlite3.IntegrityError:return jsonify(error='That category already exists'),409
@app.route('/api/admin/categories/<x>',methods=['PATCH','DELETE'])
@auth({'ADMIN'})
def cat_edit(x):
 if request.method=='DELETE':db().execute('DELETE FROM Categories WHERE category_id=?',(x,));db().commit();return {'deleted':True}
 n=str((request.get_json(silent=True)or{}).get('name','')).strip();db().execute('UPDATE Categories SET category_name=? WHERE category_id=?',(n,x));db().commit();return {'id':x,'name':n}
@app.get('/api/product-models')
def models():return jsonify([dict(x) for x in db().execute('SELECT m.*,c.category_name FROM ProductModels m JOIN Categories c ON c.category_id=m.category_id')])
@app.post('/api/product-models')
@auth()
def model_add():
 d=request.get_json(silent=True)or{};cid=d.get('category_id');name=str(d.get('model_name','')).strip();brand=str(d.get('brand','')).strip();kind=str(d.get('item_type','')).strip();desc=str(d.get('model_description','')).strip()
 if not cid or not name or not brand or not kind or not desc:return jsonify(error='Category, model name, brand, item type and description are required'),400
 x=uid();db().execute('INSERT INTO ProductModels VALUES(?,?,?,?,?,?,?)',(x,cid,name,brand,kind,desc,now()));db().commit();return {'model_id':x},201
@app.post('/api/products')
@auth()
def prod_add():
 d=request.get_json(silent=True)or{};m=d.get('model_id');cid=d.get('category_id');name=str(d.get('model_name',d.get('title',''))).strip();desc=str(d.get('model_description',d.get('description',''))).strip()
 if not m:
  if not cid or not name or not desc:return jsonify(error='Choose a model or provide its category, name and description'),400
  m=uid();db().execute('INSERT INTO ProductModels VALUES(?,?,?,?,?,?,?)',(m,cid,name,str(d.get('brand','Unspecified')),str(d.get('item_type','General')),desc,now()))
 try:price=float(d.get('price'));stock=int(d.get('on_hand_qty',d.get('quantity',1)));floor=d.get('minimum_offer_price',d.get('min_price'));floor=float(floor) if floor not in('',None) else None
 except:return jsonify(error='Enter valid price and stock'),400
 if price<=0 or stock<0 or floor is not None and not 0<floor<=price:return jsonify(error='Invalid product values'),400
 x=uid();db().execute('INSERT INTO Products VALUES(?,?,?,?,?,?,?,?,?,?,?)',(x,m,g.user['user_id'],price,str(d.get('condition','Good')),str(d.get('appearance_note',desc)),floor,stock,0,1,now()));db().commit();return jsonify(product_out(product(x))),201
@app.get('/api/products')
def prods():
 q=str(request.args.get('q','')).strip();cat=request.args.get('category');sql='''SELECT p.*,m.model_name,m.brand,m.item_type,m.model_description,c.category_name,u.name seller_name,u.reputation_score seller_reputation,u.review_count,u.is_trusted_seller FROM Products p JOIN ProductModels m ON m.model_id=p.model_id JOIN Categories c ON c.category_id=m.category_id JOIN Users u ON u.user_id=p.seller_id WHERE p.listing_enabled=1 AND p.on_hand_qty>p.reserved_qty''';a=[]
 if q:sql+=' AND (m.model_name LIKE ? OR m.brand LIKE ?)';a += ['%'+q+'%']*2
 if cat:sql+=' AND c.category_id=?';a.append(cat)
 return jsonify([product_out(x) for x in db().execute(sql,a)])
@app.get('/api/my/products')
@auth()
def my_prods():
 sql='''SELECT p.*,m.model_name,m.brand,m.item_type,m.model_description,c.category_name,u.name seller_name,u.reputation_score seller_reputation,u.review_count,u.is_trusted_seller FROM Products p JOIN ProductModels m ON m.model_id=p.model_id JOIN Categories c ON c.category_id=m.category_id JOIN Users u ON u.user_id=p.seller_id WHERE p.seller_id=?''';return jsonify([product_out(x) for x in db().execute(sql,(g.user['user_id'],))])
@app.route('/api/products/<x>',methods=['PATCH','DELETE'])
@auth()
def prod_edit(x):
 p=product(x)
 if not p or(p['seller_id']!=g.user['user_id'] and g.user['role']!='ADMIN'):return jsonify(error='Product not found'),404
 if request.method=='DELETE':db().execute('UPDATE Products SET listing_enabled=0 WHERE product_id=?',(x,));db().commit();return {'ok':True}
 d=request.get_json(silent=True)or{};fields={'price':'price','condition':'condition','appearance_note':'appearance_note','minimum_offer_price':'minimum_offer_price','on_hand_qty':'on_hand_qty','quantity':'on_hand_qty'};sets=[];args=[]
 for k,col in fields.items():
  if k in d:sets.append(col+'=?');args.append(d[k])
 if 'status'in d:sets.append('listing_enabled=?');args.append(int(d['status']=='Available'))
 if not sets:return jsonify(error='No product values supplied'),400
 db().execute('UPDATE Products SET '+','.join(sets)+' WHERE product_id=?',(*args,x));db().commit();return jsonify(product_out(product(x)))

@app.get('/api/addresses')
@auth()
def addresses():return jsonify([dict(x)|{'id':x['address_id'],'phone':x['phone_number']} for x in db().execute('SELECT * FROM Addresses WHERE user_id=?',(g.user['user_id'],))])
@app.post('/api/addresses')
@auth()
def address_add():
 d=request.get_json(silent=True)or{};f=['recipient_name','address_line','city','postcode','state','country'];vals=[str(d.get(k,'')).strip() for k in f];phone=str(d.get('phone_number',d.get('phone',''))).strip()
 if not phone or any(not x for x in vals):return jsonify(error='Complete all delivery address fields'),400
 x=uid()
 with db():
  if d.get('is_default'):db().execute('UPDATE Addresses SET is_default=0 WHERE user_id=?',(g.user['user_id'],))
  db().execute('INSERT INTO Addresses VALUES(?,?,?,?,?,?,?,?,?,?)',(x,g.user['user_id'],vals[0],phone,*vals[1:],int(bool(d.get('is_default')))))
 return {'id':x},201
@app.route('/api/addresses/<x>',methods=['PATCH','DELETE'])
@auth()
def address_edit(x):
 if request.method=='DELETE':db().execute('DELETE FROM Addresses WHERE address_id=? AND user_id=?',(x,g.user['user_id']));db().commit();return {'ok':True}
 d=request.get_json(silent=True)or{};cols={'recipient_name':'recipient_name','phone':'phone_number','phone_number':'phone_number','address_line':'address_line','city':'city','postcode':'postcode','state':'state','country':'country','is_default':'is_default'};s=[];a=[]
 for k,c in cols.items():
  if k in d and c not in [z.split('=')[0] for z in s]:s.append(c+'=?');a.append(int(bool(d[k]))if c=='is_default' else str(d[k]))
 if not s:return jsonify(error='No address values supplied'),400
 if d.get('is_default'):db().execute('UPDATE Addresses SET is_default=0 WHERE user_id=?',(g.user['user_id'],))
 db().execute('UPDATE Addresses SET '+','.join(s)+' WHERE address_id=? AND user_id=?',(*a,x,g.user['user_id']));db().commit();return {'ok':True}
@app.get('/api/wishlist')
@auth()
def wishlist():
 sql='''SELECT p.*,m.model_name,m.brand,m.item_type,m.model_description,c.category_name,u.name seller_name,u.reputation_score seller_reputation,u.review_count,u.is_trusted_seller,w.note wishlist_note FROM Wishlist w JOIN Products p ON p.product_id=w.product_id JOIN ProductModels m ON m.model_id=p.model_id JOIN Categories c ON c.category_id=m.category_id JOIN Users u ON u.user_id=p.seller_id WHERE w.user_id=?''';return jsonify([product_out(x) for x in db().execute(sql,(g.user['user_id'],))])
@app.route('/api/wishlist/<x>',methods=['POST','PATCH','DELETE'])
@auth()
def wishlist_edit(x):
 if request.method=='DELETE':db().execute('DELETE FROM Wishlist WHERE user_id=? AND product_id=?',(g.user['user_id'],x))
 elif request.method=='PATCH':db().execute('UPDATE Wishlist SET note=? WHERE user_id=? AND product_id=?',(str((request.get_json(silent=True)or{}).get('note','')),g.user['user_id'],x))
 else:
  try:db().execute('INSERT INTO Wishlist VALUES(?,?,?,?,?)',(uid(),g.user['user_id'],x,str((request.get_json(silent=True)or{}).get('note','')),now()))
  except sqlite3.IntegrityError:return jsonify(error='Already saved'),409
 db().commit();return {'ok':True}
@app.get('/api/cart')
@auth()
def cart_get():
 cid=cart(g.user['user_id']);sql='''SELECT ci.*,p.price,p.on_hand_qty,p.reserved_qty,m.model_name FROM CartItems ci JOIN Products p ON p.product_id=ci.product_id JOIN ProductModels m ON m.model_id=p.model_id WHERE ci.cart_id=?''';items=[dict(x)|{'id':x['cart_item_id'],'title':x['model_name'],'unit_price':x['price'],'stock':x['on_hand_qty']-x['reserved_qty'],'subtotal':x['quantity']*x['price']}for x in db().execute(sql,(cid,))];return jsonify(items=items,total=sum(x['subtotal'] for x in items))
@app.post('/api/cart')
@app.post('/api/cart/items')
@auth()
def cart_add():
 d=request.get_json(silent=True)or{};pid=d.get('product_id');p=product(pid,True);qty=int(d.get('quantity',1))
 if not p or qty<1:return jsonify(error='Product is unavailable'),400
 cid=cart(g.user['user_id']);r=db().execute('SELECT cart_item_id FROM CartItems WHERE cart_id=? AND product_id=?',(cid,pid)).fetchone()
 if r:db().execute("UPDATE CartItems SET quantity=?,item_status='ACTIVE',line_revision=? WHERE cart_item_id=?",(qty,uid(),r['cart_item_id']))
 else:db().execute('INSERT INTO CartItems VALUES(?,?,?,?,?,?)',(uid(),cid,pid,qty,'ACTIVE',uid()))
 db().commit();return cart_get()
@app.route('/api/cart/<x>',methods=['PATCH','DELETE'])
@app.route('/api/cart/items/<x>',methods=['PATCH','DELETE'])
@auth()
def cart_edit(x):
 cid=cart(g.user['user_id'])
 if request.method=='DELETE':db().execute('DELETE FROM CartItems WHERE cart_item_id=? AND cart_id=?',(x,cid))
 else:
  d=request.get_json(silent=True)or{};db().execute('UPDATE CartItems SET quantity=?,item_status=?,line_revision=? WHERE cart_item_id=? AND cart_id=?',(int(d.get('quantity',1)),str(d.get('item_status','ACTIVE')).upper(),uid(),x,cid))
 db().commit();return {'ok':True}
@app.post('/api/offers')
@auth()
def offer_add():
 d=request.get_json(silent=True)or{};pid=d.get('product_id');p=product(pid,True)
 try:price=float(d.get('offer_price',d.get('price')))
 except:return jsonify(error='Enter a valid offer price'),400
 if not p or p['seller_id']==g.user['user_id'] or price<=0 or p['minimum_offer_price']and price<p['minimum_offer_price']:return jsonify(error='Offer is invalid'),400
 x=uid();exp=(datetime.now(timezone.utc)+timedelta(hours=24)).isoformat();db().execute('INSERT INTO Offers VALUES(?,?,?,?,?,?,?,NULL)',(x,pid,g.user['user_id'],price,'PENDING',now(),exp));notify(p['seller_id'],'offer:'+x,'You received a new offer');db().commit();return {'id':x,'status':'Pending'},201
@app.get('/api/offers')
@auth()
def offer_list():
 sql='''SELECT o.*,m.model_name,p.seller_id FROM Offers o JOIN Products p ON p.product_id=o.product_id JOIN ProductModels m ON m.model_id=p.model_id WHERE o.buyer_id=? OR p.seller_id=?''';return jsonify([dict(x)|{'id':x['offer_id'],'price':x['offer_price'],'status':label(x['offer_status']),'title':x['model_name']}for x in db().execute(sql,(g.user['user_id'],g.user['user_id']))])
@app.route('/api/offers/<x>',methods=['PATCH','DELETE'])
@auth()
def offer_edit(x):
 r=db().execute('SELECT o.*,p.seller_id FROM Offers o JOIN Products p ON p.product_id=o.product_id WHERE o.offer_id=?',(x,)).fetchone()
 if not r:return jsonify(error='Offer not found'),404
 if request.method=='DELETE':
  if r['buyer_id']!=g.user['user_id']:return jsonify(error='Permission denied'),403
  db().execute("UPDATE Offers SET offer_status='WITHDRAWN',decided_at=? WHERE offer_id=?",(now(),x))
 else:
  a=str((request.get_json(silent=True)or{}).get('action','')).lower();v='ACCEPTED'if a=='accept'else'REJECTED'if a=='reject'else None
  if r['seller_id']!=g.user['user_id']or not v:return jsonify(error='Permission denied'),403
  db().execute('UPDATE Offers SET offer_status=?,decided_at=? WHERE offer_id=?',(v,now(),x))
 db().commit();return {'ok':True}
def total(oid):return db().execute('SELECT COALESCE(SUM(quantity*unit_price_snapshot),0)v FROM OrderItems WHERE order_id=?',(oid,)).fetchone()['v']
@app.post('/api/orders')
@auth()
def order_add():
 cid=cart(g.user['user_id']);items=db().execute("SELECT * FROM CartItems WHERE cart_id=? AND item_status='ACTIVE'",(cid,)).fetchall();d=request.get_json(silent=True)or{}
 if not items:return jsonify(error='Your cart is empty'),400
 ps=[product(i['product_id'],True)for i in items]
 if any(p is None for p in ps)or len({p['seller_id']for p in ps})!=1:return jsonify(error='Use available products from one seller'),400
 a=db().execute('SELECT * FROM Addresses WHERE address_id=? AND user_id=?',(d.get('address_id'),g.user['user_id'])).fetchone()
 if not a:return jsonify(error='Choose a delivery address'),400
 x=uid();db().execute('INSERT INTO Orders VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(x,g.user['user_id'],ps[0]['seller_id'],a['address_id'],'PENDING',now(),(datetime.now(timezone.utc)+timedelta(minutes=30)).isoformat(),None,a['recipient_name'],a['phone_number'],a['address_line'],a['city'],a['postcode'],a['state'],a['country']))
 for i,p in zip(items,ps):
  if i['quantity']>p['on_hand_qty']-p['reserved_qty']:return jsonify(error='Insufficient stock'),409
  oi=uid();db().execute('INSERT INTO OrderItems VALUES(?,?,?,?,?,?)',(oi,x,i['product_id'],i['quantity'],p['price'],i['line_revision']));db().execute('UPDATE Products SET reserved_qty=reserved_qty+? WHERE product_id=?',(i['quantity'],i['product_id']));db().execute('DELETE FROM CartItems WHERE cart_item_id=?',(i['cart_item_id'],))
 db().execute('INSERT INTO Payments VALUES(?,?,?,?,?,?,?,?,?,?)',(uid(),x,total(x),None,'PENDING',None,'NONE',None,None,None));did=uid();db().execute('INSERT INTO Deliveries VALUES(?,?,?,?,?,?,?,?)',(did,x,'SL'+secrets.token_hex(4).upper(),'SecondLife Delivery','PENDING',None,None,None));event(did,'TRACKING_NUMBER_RECORDED','SELLER');db().commit();return {'id':x,'order_id':x,'total':total(x)},201
@app.get('/api/orders')
@auth()
def order_list():
 rows=db().execute('SELECT o.*,d.delivery_status,d.tracking_number FROM Orders o LEFT JOIN Deliveries d ON d.order_id=o.order_id WHERE o.buyer_id=? OR o.seller_id=? ORDER BY o.created_at DESC',(g.user['user_id'],g.user['user_id'])).fetchall();o=[]
 for r in rows:
  d=dict(r);d.update(id=d['order_id'],status=label(d['order_status']),total=total(d['order_id']),items=[dict(i)|{'title':i['model_name']}for i in db().execute('SELECT oi.*,m.model_name FROM OrderItems oi JOIN Products p ON p.product_id=oi.product_id JOIN ProductModels m ON m.model_id=p.model_id WHERE oi.order_id=?',(d['order_id'],))]);o.append(d)
 return jsonify(o)
@app.post('/api/orders/<x>/pay')
@auth()
def order_pay(x):
 r=db().execute("SELECT * FROM Orders WHERE order_id=? AND buyer_id=? AND order_status='PENDING'",(x,g.user['user_id'])).fetchone()
 if not r:return jsonify(error='Order cannot be paid'),409
 db().execute("UPDATE Orders SET order_status='PAID' WHERE order_id=?",(x,));db().execute("UPDATE Payments SET payment_status='PAID',payment_method=?,paid_at=? WHERE order_id=?",(str((request.get_json(silent=True)or{}).get('method','Simulated')),now(),x));db().commit();return {'ok':True}
@app.route('/api/orders/<x>/cancel',methods=['POST','DELETE'])
@auth()
def order_cancel(x):
 r=db().execute("SELECT * FROM Orders WHERE order_id=? AND order_status='PENDING'",(x,)).fetchone()
 if not r or g.user['user_id'] not in(r['buyer_id'],r['seller_id']):return jsonify(error='Only a pending order can be cancelled'),409
 db().execute("UPDATE Orders SET order_status='CANCELLED',cancellation_reason=? WHERE order_id=?",(str((request.get_json(silent=True)or{}).get('reason','Cancelled by user')),x))
 for item in db().execute('SELECT product_id,quantity FROM OrderItems WHERE order_id=?',(x,)):db().execute('UPDATE Products SET reserved_qty=MAX(0,reserved_qty-?) WHERE product_id=?',(item['quantity'],item['product_id']))
 db().execute("UPDATE Payments SET payment_status='FAILED' WHERE order_id=?",(x,));db().commit();return {'ok':True}
@app.post('/api/orders/<x>/confirm')
@auth()
def order_confirm(x):
 r=db().execute("SELECT * FROM Orders WHERE order_id=? AND buyer_id=? AND order_status='PAID'",(x,g.user['user_id'])).fetchone()
 if not r:return jsonify(error='Order cannot be confirmed'),409
 did=db().execute('SELECT delivery_id FROM Deliveries WHERE order_id=?',(x,)).fetchone()['delivery_id'];db().execute("UPDATE Orders SET order_status='COMPLETED' WHERE order_id=?",(x,));db().execute("UPDATE Deliveries SET delivery_status='DELIVERED',delivered_at=?,receipt_confirmed_at=? WHERE delivery_id=?",(now(),now(),did));event(did,'DELIVERED');event(did,'RECEIPT_CONFIRMED','BUYER');db().commit();return {'ok':True}
@app.get('/api/payments')
@auth()
def payments():return jsonify([dict(x)|{'id':x['payment_id'],'status':label(x['payment_status']),'method':x['payment_method'] or 'Simulated'}for x in db().execute('SELECT p.* FROM Payments p JOIN Orders o ON o.order_id=p.order_id WHERE o.buyer_id=? OR o.seller_id=?',(g.user['user_id'],g.user['user_id']))])
@app.get('/api/deliveries')
@auth()
def deliveries():
 rows=db().execute('SELECT d.*,o.buyer_id,o.seller_id FROM Deliveries d JOIN Orders o ON o.order_id=d.order_id WHERE o.buyer_id=? OR o.seller_id=?',(g.user['user_id'],g.user['user_id']));return jsonify([dict(r)|{'id':r['delivery_id'],'status':label(r['delivery_status']),'courier':r['courier_name'],'events':[dict(e)for e in db().execute('SELECT event_type,event_time,source FROM TrackingEvents WHERE delivery_id=?',(r['delivery_id'],))]}for r in rows])
@app.patch('/api/deliveries/<x>')
@auth()
def delivery_update(x):
 d=request.get_json(silent=True)or{};s=str(d.get('status','')).upper().replace(' ','_');r=db().execute('SELECT d.*,o.seller_id FROM Deliveries d JOIN Orders o ON o.order_id=d.order_id WHERE d.delivery_id=?',(x,)).fetchone()
 if not r or r['seller_id']!=g.user['user_id']or s not in('SHIPPED','IN_TRANSIT','DELIVERED'):return jsonify(error='Delivery cannot be updated'),400
 col={'SHIPPED':'shipped_at','DELIVERED':'delivered_at'}.get(s);sql='UPDATE Deliveries SET delivery_status=?'+(','+col+'=?'if col else '')+' WHERE delivery_id=?';a=[s]+([now()]if col else[])+[x];db().execute(sql,a);event(x,s,'SELLER');db().commit();return {'ok':True}
@app.post('/api/reviews')
@auth()
def review_add():
 d=request.get_json(silent=True)or{};o=db().execute("SELECT * FROM Orders WHERE order_id=? AND order_status='COMPLETED'",(d.get('order_id'),)).fetchone()
 if not o or g.user['user_id']not in(o['buyer_id'],o['seller_id']):return jsonify(error='Reviews require a completed order'),403
 try:rating=int(d.get('rating'))
 except:return jsonify(error='Rating must be 1 to 5'),400
 if rating not in range(1,6):return jsonify(error='Rating must be 1 to 5'),400
 db().execute('INSERT INTO Reviews VALUES(?,?,?,?,?,?,NULL)',(uid(),o['order_id'],g.user['user_id'],rating,str(d.get('comment','')),now()));db().commit();return {'ok':True},201
@app.get('/api/reviews')
def reviews():
 sql='''SELECT r.*,u.name reviewer_name,o.buyer_id,o.seller_id FROM Reviews r JOIN Users u ON u.user_id=r.reviewer_id JOIN Orders o ON o.order_id=r.order_id WHERE r.removed_at IS NULL'''
 return jsonify([dict(r)|{'id':r['review_id'],'reviewee_id':r['seller_id'] if r['reviewer_id']==r['buyer_id'] else r['buyer_id']}for r in db().execute(sql)])
@app.route('/api/reviews/<x>',methods=['PATCH','DELETE'])
@auth()
def review_edit(x):
 r=db().execute('SELECT * FROM Reviews WHERE review_id=? AND reviewer_id=?',(x,g.user['user_id'])).fetchone()
 if not r:return jsonify(error='Review not found'),404
 if request.method=='DELETE':db().execute('UPDATE Reviews SET removed_at=? WHERE review_id=?',(now(),x))
 else:
  d=request.get_json(silent=True)or{};rating=int(d.get('rating',r['rating']))
  if rating not in range(1,6):return jsonify(error='Rating must be 1 to 5'),400
  db().execute('UPDATE Reviews SET rating=?,comment=? WHERE review_id=?',(rating,str(d.get('comment',r['comment'])),x))
 db().commit();return {'ok':True}
@app.post('/api/reports')
@auth()
def report_add():
 d=request.get_json(silent=True)or{};typ=str(d.get('case_type','')).upper();typ=typ or ('ORDER_DISPUTE' if d.get('order_id') else 'PRODUCT_REPORT' if d.get('product_id') else 'USER_REPORT' if d.get('reported_user_id') else '');key={'USER_REPORT':'reported_user_id','PRODUCT_REPORT':'product_id','ORDER_DISPUTE':'order_id'}.get(typ)
 if not key or not d.get(key)or not str(d.get('description','')).strip():return jsonify(error='Provide case type, related item and description'),400
 v={'order_id':None,'reported_user_id':None,'product_id':None};v[key]=d[key];x=uid();db().execute('INSERT INTO ReportsDisputes VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(x,v['order_id'],g.user['user_id'],v['reported_user_id'],v['product_id'],typ,str(d['description']), 'PENDING',None,None,now(),None));db().commit();return {'id':x,'status':'PENDING'},201
@app.get('/api/reports')
@auth()
def reports():return jsonify([dict(r)|{'id':r['case_id'],'status':label(r['case_status']),'report_type':r['case_type']}for r in db().execute('SELECT * FROM ReportsDisputes WHERE reporter_id=?',(g.user['user_id'],))])
@app.route('/api/reports/<x>',methods=['PATCH','DELETE'])
@auth()
def report_edit(x):
 if request.method=='DELETE':db().execute("UPDATE ReportsDisputes SET case_status='WITHDRAWN' WHERE case_id=? AND reporter_id=? AND case_status='PENDING'",(x,g.user['user_id']))
 else:db().execute("UPDATE ReportsDisputes SET description=? WHERE case_id=? AND reporter_id=? AND case_status='PENDING'",(str((request.get_json(silent=True)or{}).get('description','')).strip(),x,g.user['user_id']))
 db().commit();return {'ok':True}
@app.get('/api/notifications')
@auth()
def notes():return jsonify([dict(r)|{'id':r['notification_id'],'is_read':bool(r['read_at'])}for r in db().execute('SELECT * FROM Notifications WHERE recipient_id=?',(g.user['user_id'],))])
@app.post('/api/notifications/read')
@auth()
def notes_read():db().execute('UPDATE Notifications SET read_at=? WHERE recipient_id=?',(now(),g.user['user_id']));db().commit();return {'ok':True}
@app.get('/api/admin/summary')
@auth({'ADMIN'})
def admin_summary():
 c=db();return jsonify(users=c.execute('SELECT COUNT(*)FROM Users').fetchone()[0],active_products=c.execute('SELECT COUNT(*)FROM Products WHERE listing_enabled=1').fetchone()[0],orders=c.execute('SELECT COUNT(*)FROM Orders').fetchone()[0],open_reports=c.execute("SELECT COUNT(*)FROM ReportsDisputes WHERE case_status='PENDING'").fetchone()[0],gross_sales=c.execute("SELECT COALESCE(SUM(amount),0)FROM Payments WHERE payment_status='PAID'").fetchone()[0])
@app.get('/api/admin/users')
@auth({'ADMIN'})
def admin_users():return jsonify([user_out(r)for r in db().execute('SELECT * FROM Users')])
@app.patch('/api/admin/users/<x>')
@auth({'ADMIN'})
def admin_user(x):
 s=str((request.get_json(silent=True)or{}).get('status','ACTIVE')).upper();s='DEACTIVATED'if s in('SUSPENDED','DEACTIVATED')else'ACTIVE';db().execute('UPDATE Users SET account_status=? WHERE user_id=?',(s,x));db().commit();return {'ok':True}
@app.get('/api/admin/reports')
@auth({'ADMIN'})
def admin_reports():return jsonify([dict(r)|{'id':r['case_id'],'status':label(r['case_status']),'report_type':r['case_type']}for r in db().execute('SELECT * FROM ReportsDisputes')])
@app.patch('/api/admin/reports/<x>')
@auth({'ADMIN'})
def admin_report(x):
 d=request.get_json(silent=True)or{};s=str(d.get('status','RESOLVED')).upper().replace(' ','_');db().execute('UPDATE ReportsDisputes SET case_status=?,resolved_by=?,resolution_note=?,resolved_at=? WHERE case_id=?',(s,g.user['user_id'],str(d.get('resolution','')),now()if s=='RESOLVED'else None,x));db().commit();return {'ok':True}
@app.get('/')
def index():return send_from_directory(app.static_folder,'index.html')
@app.get('/<path:path>')
def frontend_file(path):return send_from_directory(app.static_folder,path)
init()
if __name__=='__main__':app.run(host=os.getenv('HOST','127.0.0.1'),port=int(os.getenv('PORT','5000')),debug=False)
