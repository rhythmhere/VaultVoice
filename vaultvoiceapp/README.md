# VaultVoice survivor app

This is the survivor-only Flutter client for VaultVoice Nepal. It does not contain NGO, admin, donation, crowdfunding, commission, or billing workflows.

## Run

From `vaultvoiceapp`:

```powershell
flutter pub get
flutter run --dart-define=API_BASE_URL=http://localhost:8000
```

For a tunnel or deployed API, change only the define:

```powershell
flutter run --dart-define=API_BASE_URL=https://your-tunnel-url.trycloudflare.com
```

Production must use HTTPS. No secret, case token, SOS token, evidence, note, or location is placed in source, shared preferences, logs, analytics, or crash payloads.

## Architecture

`core/config` owns the API URL; `core/network` owns Dio and bearer injection; `core/storage` owns secure storage; `repositories` own API calls; `models` own DTO parsing; `widgets` contains the persistent Quick Exit/SOS safety controls; `screens` owns survivor workflows. Riverpod is available for dependency injection, and the routing surface is intentionally small during active reporting so the workflow has no persistent bottom navigation.

## Route map

`/` home, `/report` anonymous case creation, `/recover` Case ID recovery, `/neutral` Quick Exit destination. The active case surface is opened after session creation. SOS is a modal sheet reachable from every survivor screen and works before a case exists.

## API DTO map

`CaseCreate`: `category`, `district`, `initial_report`, `clarifying_qa`, `emergency_requested`.

`AuthLogin`: `identifier`; response stores `session_token` and `expires_at` securely.

`ClarifyRequest`: `question`, `answer`.

`ReferralCreate`: `ngo_id`, `consent_scope`, `submitted_message`, `consent_confirmed`, `includes_evidence`, `evidence_refs`.

`SOSCreate`: optional `case_id`, `note`, `latitude`, `longitude`, `accuracy`, `captured_at`, `location_status`, and `location_source`. The returned `access_token` is stored separately from the case session token.

Evidence uses multipart `POST /api/cases/{id}/evidence` and authenticated decrypted download `GET /api/cases/{id}/evidence/{evidence_id}`. The presigned URL endpoint is intentionally not used.

## Verification

Run `flutter analyze` and `flutter test`. Backend verification from the repository root is `$env:PYTHONPATH='.'; pytest -q`.
