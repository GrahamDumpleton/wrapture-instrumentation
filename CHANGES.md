# Changes

## Version 1.0.0

In development.

- Project skeleton: the `wrapture_instrumentation` package with its
  version, the test-side WSGI driver, and the package-level tests
  that keep every registered instrumentation import-light.

- Flask (`flask`, Flask 3.x): every application's `wsgi_app` wrapped in
  the recording WSGI middleware at construction, every view function
  observed as it registers, and the exception `Flask.handle_exception`
  receives noted against the request event. No settings yet.

- Flask requests are annotated with the matched route pattern and
  endpoint once routing resolves, the low-cardinality grouping key
  the raw path is not, and observed views are labelled by their
  endpoint, so a `MethodView` reads as its registered name and a
  blueprint view by its dotted endpoint.
