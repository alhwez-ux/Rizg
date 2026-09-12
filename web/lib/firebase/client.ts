import { type FirebaseApp, getApp, getApps, initializeApp } from "firebase/app";
import { doc, type Firestore, getFirestore } from "firebase/firestore";

const firebaseConfig = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
  storageBucket: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID,
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
};

export const STOCKS_COLLECTION = "stocks";
export const HISTORY_SUBCOLLECTION = "history";
export const DIVIDENDS_SUBCOLLECTION = "dividends";

export function isFirebaseConfigured(): boolean {
  return Boolean(firebaseConfig.apiKey && firebaseConfig.projectId);
}

export function assertFirebaseConfig(): void {
  if (!isFirebaseConfigured()) {
    throw new Error(
      "Firebase is not configured. Copy web/.env.example to web/.env.local and set NEXT_PUBLIC_FIREBASE_*.",
    );
  }
}

export function getFirebaseApp(): FirebaseApp {
  assertFirebaseConfig();
  if (getApps().length > 0) {
    return getApp();
  }
  return initializeApp(firebaseConfig);
}

export function getDb(): Firestore {
  return getFirestore(getFirebaseApp());
}

export function stockDocRef(symbol: string) {
  return doc(getDb(), STOCKS_COLLECTION, symbol);
}

export function historyDocRef(symbol: string, quarter: string) {
  return doc(getDb(), STOCKS_COLLECTION, symbol, HISTORY_SUBCOLLECTION, quarter);
}

export function dividendDocRef(symbol: string, dividendId: string) {
  return doc(getDb(), STOCKS_COLLECTION, symbol, DIVIDENDS_SUBCOLLECTION, dividendId);
}
