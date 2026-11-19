# Stock Insights mobile app (Expo)

The phone app for the Stock Insights backend. First version: sign in, watchlists with prices,
stock detail (why it moved, AI explanation, peers, moving averages, headlines), and alerts
(add, turn off or on, remove, email settings, history).

## Run it on your iPhone with Expo Go

1. Install **Expo Go** from the App Store on your iPhone.
2. On your Mac, in this folder:
   ```
   cd mobile
   npm install
   npx expo start
   ```
3. Scan the QR code with the iPhone Camera app and open it in Expo Go.
   Your phone and Mac must be on the same Wi-Fi. If the QR code doesn't connect, run
   `npx expo start --tunnel` instead.

The app talks to the live backend on Railway by default. To use another backend, set
`EXPO_PUBLIC_API_URL` before starting, for example
`EXPO_PUBLIC_API_URL=http://192.168.1.20:8001 npx expo start`.

## Notes
- You sign in with the same account as the website; your watchlists and alerts are shared.
- Press and hold a stock in the watchlist to remove it.
- Creating or renaming watchlists, the chat, and CSV downloads are on the website for now.
