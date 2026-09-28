package org.thehill.hill175.auth.sso;

/** Safe user-facing error; never wrap an upstream response containing tokens. */
public final class SsoException extends RuntimeException {
    public SsoException(String message) { super(message); }
}
