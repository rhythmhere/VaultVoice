import 'package:dio/dio.dart';
import 'package:file_picker/file_picker.dart';
import '../core/network/dio_client.dart';
import '../core/storage/secure_store.dart';
import '../models/case_model.dart';

class VaultRepository {
  VaultRepository(this.client, this.store);
  final DioClient client;
  final SecureStore store;
  Future<CaseModel> create({
    required String category,
    required String district,
    required String report,
    required bool emergency,
  }) async {
    final r = await client.dio.post(
      '/api/cases',
      data: {
        'category': category,
        'district': district,
        'initial_report': report,
        'clarifying_qa': [],
        'emergency_requested': emergency,
      },
    );
    await _saveSession(r.data);
    return CaseModel.fromJson(r.data);
  }

  Future<CaseModel> login(String id) async {
    final r = await client.dio.post(
      '/api/auth/login',
      data: {'identifier': id.trim().toUpperCase()},
    );
    await store.write(SecureStore.caseId, id.trim().toUpperCase());
    await store.write(SecureStore.sessionToken, r.data['session_token']);
    await store.write(SecureStore.sessionExpiry, r.data['expires_at']);
    return getCase(id);
  }

  Future<CaseModel> getCase(String id) async => CaseModel.fromJson(
    (await client.dio.get('/api/cases/${id.toUpperCase()}')).data,
  );
  Future<Map<String, dynamic>> clarify(
    String id,
    String question,
    String answer,
  ) async => (await client.dio.post(
    '/api/cases/$id/clarify',
    data: {'question': question, 'answer': answer},
  )).data;
  Future<void> _saveSession(Map<String, dynamic> j) async {
    await store.write(SecureStore.caseId, j['case_id']);
    await store.write(SecureStore.sessionToken, j['session_token']);
    await store.write(SecureStore.sessionExpiry, j['session_expires_at']);
  }

  Future<Map<String, dynamic>> sendSos({
    String? caseId,
    String? note,
    double? latitude,
    double? longitude,
    double? accuracy,
    String locationStatus = 'not_requested',
    DateTime? capturedAt,
  }) async {
    final data = <String, dynamic>{
      'case_id': caseId,
      'note': note,
      'latitude': latitude,
      'longitude': longitude,
      'accuracy': accuracy,
      'location_status': locationStatus,
      'location_source': latitude == null ? 'unknown' : 'gps',
    };
    if (capturedAt != null)
      data['captured_at'] = capturedAt.toUtc().toIso8601String();
    data.removeWhere((_, v) => v == null);
    final r = await client.dio.post(
      '/api/sos',
      data: data,
      options: Options(headers: {'Authorization': null}),
    );
    await store.write(SecureStore.sosId, r.data['id']);
    await store.write(SecureStore.sosToken, r.data['access_token']);
    return Map<String, dynamic>.from(r.data);
  }

  Future<List<Map<String, dynamic>>> matches(String id) async =>
      ((await client.dio.get('/api/cases/$id/matches')).data as List)
          .map((e) => Map<String, dynamic>.from(e))
          .toList();
  Future<Map<String, dynamic>> referral(
    String id,
    Map<String, dynamic> data,
  ) async => Map<String, dynamic>.from(
    (await client.dio.post('/api/cases/$id/referrals', data: data)).data,
  );
  Future<List<Map<String, dynamic>>> messages(String id) async =>
      ((await client.dio.get('/api/cases/$id/messages')).data as List)
          .map((e) => Map<String, dynamic>.from(e))
          .toList();
  Future<Map<String, dynamic>> sendMessage(String id, String message) async =>
      Map<String, dynamic>.from(
        (await client.dio.post(
          '/api/cases/$id/messages',
          data: {'message': message, 'is_internal_note': false},
        )).data,
      );
  Future<List<Map<String, dynamic>>> referrals(String id) async =>
      ((await client.dio.get('/api/cases/$id/referrals')).data as List)
          .map((e) => Map<String, dynamic>.from(e))
          .toList();
  Future<Map<String, dynamic>> status(String id, String value) async =>
      Map<String, dynamic>.from(
        (await client.dio.patch(
          '/api/cases/$id/status',
          data: {'status': value},
        )).data,
      );
  Future<Map<String, dynamic>> timeline(String id) async =>
      Map<String, dynamic>.from(
        (await client.dio.post('/api/cases/$id/timeline')).data,
      );
  Future<Map<String, dynamic>> uploadEvidence(
    String id,
    PlatformFile file, {
    String description = '',
    String? incidentDate,
    ProgressCallback? onProgress,
  }) async {
    final fields = <String, dynamic>{
      'file': await MultipartFile.fromFile(file.path!, filename: file.name),
      'description': description,
    };
    if (incidentDate != null) fields['incident_date'] = incidentDate;
    final form = FormData.fromMap(fields);
    return Map<String, dynamic>.from(
      (await client.dio.post(
        '/api/cases/$id/evidence',
        data: form,
        onSendProgress: onProgress,
      )).data,
    );
  }

  Future<List<int>> downloadEvidence(String id, int evidenceId) async =>
      (await client.dio.get<List<int>>(
        '/api/cases/$id/evidence/$evidenceId',
        options: Options(responseType: ResponseType.bytes),
      )).data ??
      <int>[];
  Future<Map<String, dynamic>> donate({
    required double amount,
    String? name,
    String? email,
    bool anonymous = true,
    String? message,
  }) async => Map<String, dynamic>.from(
    (await client.dio.post(
      '/api/donations/platform',
      data: {
        'amount': amount,
        'donor_name': name,
        'donor_email': email,
        'is_anonymous': anonymous,
        'currency': 'NPR',
        'message': message,
      },
    )).data,
  );
}
