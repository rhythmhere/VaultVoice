import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class SecureStore {
  SecureStore([FlutterSecureStorage? storage])
    : _storage = storage ?? const FlutterSecureStorage();
  final FlutterSecureStorage _storage;
  static const caseId = 'case_id';
  static const sessionToken = 'session_token';
  static const sessionExpiry = 'session_expiry';
  static const sosToken = 'sos_token';
  static const sosId = 'sos_id';
  Future<String?> read(String key) => _storage.read(key: key);
  Future<void> write(String key, String value) =>
      _storage.write(key: key, value: value);
  Future<void> clear() => _storage.deleteAll();
  Future<void> clearCase() async {
    for (final key in [caseId, sessionToken, sessionExpiry]) {
      await _storage.delete(key: key);
    }
  }
}
