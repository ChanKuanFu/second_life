# SecondLife — second-hand community marketplace

An implementation starter based on the modules, ERD and table definitions in the supplied mini-project brief. The responsive web client also runs inside the Kotlin Android WebView shell, so both clients use the same Python API.

## Stack

- Web: HTML5, CSS3, vanilla JavaScript
- Android: Kotlin + Android WebView
- Backend: Python 3 + Flask REST API
- Local database: SQLite, created automatically at `secondlife_current_erd.db`

The implementation uses the current ERD as its source of truth. The local development build uses UUID strings in SQLite. Its tables are `Users`, `Categories`, `ProductModels`, `Products`, `Addresses`, `Cart`, `CartItems`, `Offers`, `Orders`, `OrderItems`, `OfferRedemptions`, `Payments`, `Deliveries`, `TrackingEvents`, `Notifications`, `ReportsDisputes`, `Reviews`, and `Wishlist`. The previous `local.db` is retained only as an untouched backup and is no longer used.

The local schema follows the revised ERD while retaining the original `id`, `status`, and field names used by the existing API. ERD names such as `user_id`, `product_id`, `offer_price`, `payment_method`, and `reputation_score` are mirrored for compatibility. On the next backend start, SQLite adds the ERD columns in place and creates a `local.before-erd-<timestamp>.db` backup before migrating a legacy database.

## Start locally

On Windows, double-click `CLICK_TO_RUN_SECOND_LIFE.bat` in this project folder (or use the copy in the parent `outputs/` folder). It uses the regular Windows Python 3.12 installation at `%LOCALAPPDATA%\Programs\Python\Python312\python.exe`, creates `.venv-local` on first launch, and installs Flask dependencies if needed. The launcher waits for the API health check before opening the website.

Keep the visible **SecondLife API** window open while using the site. Press `Ctrl+C` in that window to stop the server. The local development server binds to `127.0.0.1` only.

After replacing project files, stop the old API process and start the launcher again so Flask loads the updated code and applies the database migration. Keep `local.db` in the project folder; the migration makes a timestamped backup automatically.

Manual start from this folder (using the generated local environment):

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m venv .venv-local
.\.venv-local\Scripts\python.exe -m pip install Flask==3.1.2 Flask-Cors==6.0.1
.\.venv-local\Scripts\python.exe backend\app.py
```

Open `http://127.0.0.1:5000`. API health check: `http://127.0.0.1:5000/api/health`.

Demo accounts:

- Buyer: `aina@example.com` / `demo123`
- Seller: `jason@example.com` / `demo123`
- Admin: `admin@example.com` / `admin123`

The seeded RM prices and sample listings are illustrative. Payments are simulated; do not enter real card details.

## Android

Open the `android/` directory in Android Studio and run the `app` configuration on an emulator. The default emulator URL is `http://10.0.2.2:5000/`.

For a physical phone on the same Wi-Fi, override the URL with your computer's LAN address, e.g. `-PsecondlifeWebUrl=http://192.168.1.20:5000/`. For a hosted build, use the deployed HTTPS URL. The cleartext setting is enabled for local development; turn it off for a release build served over HTTPS.

## Eight project modules

- **User & Account Management:** register, view/update profile, deactivate account and manage addresses
- **Product Listing & Inventory Management:** create, view, edit and remove listings with stock validation
- **Product Discovery & Wishlist Management:** search/filter; add, view, edit notes and remove saved products
- **Shopping Cart & Offer Management:** cart item CRUD, minimum-price offer validation, accept/reject/withdraw, automatic 24-hour offer expiry
- **Order & Payment Management:** create/read/update/cancel orders, simulated payment history and automatic unpaid-order expiry with stock release
- **Review & Dispute Management:** review CRUD with reputation recalculation; create/edit/withdraw reports
- **Admin & Platform Management:** category CRUD, user suspension/restoration, report moderation/refunds and platform statistics
- **Delivery & Transaction Management:** tracking, receipt confirmation, cancel before shipment and automatic delivery status progression
- Shared navigation and responsive web UI; the Kotlin Android WebView uses the same pages and Python API

Seller trust rule: the trusted badge appears after at least 3 reviews and a 4.5/5 average. Simulated delivery advances one stage every 30 seconds after payment by default; set `DELIVERY_STAGE_SECONDS` lower for a classroom demonstration. Expiry and delivery progression are processed when the API receives a request.

API requests use JSON. Authenticated requests send `Authorization: Bearer <token>`.

## Main endpoints

`/api/auth/register`, `/api/auth/login`, `/api/me`, `/api/addresses`, `/api/products`, `/api/categories`, `/api/wishlist`, `/api/cart`, `/api/offers`, `/api/orders`, `/api/deliveries`, `/api/reviews`, `/api/reports`, `/api/notifications`, `/api/admin/summary`, `/api/admin/users`, `/api/admin/reports`.

`render.yaml` provides a starter Render web-service definition. For deployment set `PORT` as provided by the host. Configure HTTPS and a durable PostgreSQL database before production use. Passwords are PBKDF2-hashed; payment and email/SMS notification delivery are simulated. Offer, unpaid-order and delivery automation is applied when API traffic arrives.
