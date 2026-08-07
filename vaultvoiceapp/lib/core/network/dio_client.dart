import 'dart:async';

import 'package:dio/dio.dart';
import '../config/api_config.dart';
import '../storage/secure_store.dart';

class DioClient {
  DioClient(this.store)
    : dio = Dio(
        BaseOptions(
          baseUrl: ApiConfig.baseUrl,
          // Public/mobile networks often need more than one connection attempt.
          // Keep all limits bounded so a genuinely unavailable API still fails.
          connectTimeout: const Duration(seconds: 20),
          sendTimeout: const Duration(seconds: 30),
          receiveTimeout: const Duration(seconds: 60),
          headers: {
            'Accept': 'application/json',
            'ngrok-skip-browser-warning': 'true',
          },
        ),
      ) {
    dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) async {
          final token = await store.read(SecureStore.sessionToken);
          if (token != null && token.isNotEmpty)
            options.headers['Authorization'] = 'Bearer $token';
          handler.next(options);
        },
        onError: (error, handler) async {
          final options = error.requestOptions;
          final retryCount = (options.extra['_vvRetryCount'] as int?) ?? 0;
          final canRetry =
              options.method == 'GET' ||
              options.method == 'HEAD' ||
              options.extra['retrySafe'] == true;
          final transient =
              error.type == DioExceptionType.connectionTimeout ||
              error.type == DioExceptionType.connectionError ||
              error.type == DioExceptionType.receiveTimeout ||
              error.type == DioExceptionType.sendTimeout;

          if (canRetry && transient && retryCount < 2) {
            options.extra['_vvRetryCount'] = retryCount + 1;
            await Future<void>.delayed(
              Duration(milliseconds: 500 * (retryCount + 1)),
            );
            try {
              final response = await dio.fetch<dynamic>(options);
              return handler.resolve(response);
            } on DioException catch (retryError) {
              return handler.next(retryError);
            }
          }
          handler.next(error);
        },
      ),
    );
  }
  final SecureStore store;
  final Dio dio;

  static String userMessage(Object error) {
    if (error is DioException) {
      switch (error.type) {
        case DioExceptionType.connectionTimeout:
        case DioExceptionType.sendTimeout:
        case DioExceptionType.receiveTimeout:
          return 'The connection is taking too long. Check your internet and try again.';
        case DioExceptionType.connectionError:
          return 'VaultVoice could not reach the server. Check your internet and try again.';
        case DioExceptionType.badResponse:
          final data = error.response?.data;
          final detail = data is Map ? data['detail']?.toString() : null;
          return detail?.isNotEmpty == true
              ? detail!
              : 'The server could not complete that request. Please try again.';
        case DioExceptionType.cancel:
          return 'The request was cancelled.';
        default:
          return 'Something went wrong while contacting VaultVoice.';
      }
    }
    return error.toString().replaceFirst('Exception: ', '');
  }
}
