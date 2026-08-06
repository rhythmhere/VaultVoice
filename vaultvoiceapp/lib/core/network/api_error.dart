class ApiError implements Exception {
  const ApiError(this.message, {this.statusCode});
  final String message;
  final int? statusCode;
  @override
  String toString() => message;
  static ApiError from(Object error) =>
      ApiError(error.toString().replaceFirst('Exception: ', ''));
}
