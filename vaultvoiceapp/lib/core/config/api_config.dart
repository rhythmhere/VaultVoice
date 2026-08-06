class ApiConfig {
  static const baseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'https://handclasp-resubmit-suspense.ngrok-free.dev',
  );
}
