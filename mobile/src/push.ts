export async function registerPush(_portalToken: string): Promise<void> {
  // Sin expo-notifications / FCM: el APK tiene que abrir. El push vuelve
  // cuando haya google-services.json de Firebase.
}
