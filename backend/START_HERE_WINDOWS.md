# Open this project on Windows

1. Open https://github.com/nicho-mt/Repo2/tree/m1-backend-starter and sign in if needed.
2. Click **Code -> Download ZIP**.
3. In Downloads, right-click the ZIP and choose **Extract All**.
4. Open the extracted folder containing `START_WINDOWS.cmd`, `README.md`, and `app`.
   GitHub may put this folder one level inside your extraction destination.
5. Install Python 3.12 from https://www.python.org/downloads/ if Python is not installed.
   Keep the Python launcher enabled during installation.
6. Double-click **START_WINDOWS.cmd**. It installs the dependencies, migrates the database,
   seeds synthetic records and starts the API. The first run needs internet access.
7. Keep the terminal window open. Once it reports startup complete, open
   **http://127.0.0.1:8000/docs** in your browser.
8. Expand **GET /api/v1/products -> Try it out -> Execute**. Expect four demo products.

To edit the code, open VS Code -> File -> Open Folder and choose that same extracted folder.
Read **README.md** for the detailed M1 explanation and day-by-day guide.

The cloud workspace path shown in the earlier chat is not a folder on your Windows laptop.
Use this downloaded folder's actual location. No manually typed cloud path is needed.

The API is a demonstration without authentication. No real customer data, emails, supplier
orders or payments are used. M2's FEFO and M3's forecasting remain explicit integration hooks.

The backend's 20 automated checks were verified on Linux/Python 3.12. The Windows launcher
is supplied for local setup; it has not been executed on Windows in the cloud session.
