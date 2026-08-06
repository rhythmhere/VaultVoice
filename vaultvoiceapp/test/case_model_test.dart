import 'package:flutter_test/flutter_test.dart';
import 'package:vaultvoiceapp/models/case_model.dart';

void main() {
  test('preserves failed analysis as a saved case state', () {
    final model = CaseModel.fromJson({'case_id': 'VV-12345678', 'analysis_status': 'failed', 'initial_report': 'private'});
    expect(model.id, 'VV-12345678');
    expect(model.analysisStatus, 'failed');
    expect(model.report, 'private');
  });
}
