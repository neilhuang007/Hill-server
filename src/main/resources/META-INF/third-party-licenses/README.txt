Hill 175 bundled runtime dependencies

The plugin JAR includes unmodified classes from these Maven Central artifacts.
Paper and test dependencies are not bundled. License identifiers were checked
against the published artifact POMs; source headers supplied copyright notices.
The full license texts are included alongside this file.

Apache License 2.0 (Apache-2.0.txt):

com.nimbusds:oauth2-oidc-sdk:11.38.2
com.nimbusds:nimbus-jose-jwt:10.9.1
Copyright Connect2id Ltd and contributors.
https://connect2id.com/products/nimbus-oauth-openid-connect-sdk
https://connect2id.com/products/nimbus-jose-jwt

The Nimbus JOSE JAR additionally contains shaded copies of:
com.google.code.gson:gson:2.13.1 (Copyright Google Inc.)
https://github.com/google/gson
com.github.stephenc.jcip:jcip-annotations:1.0-1 (credited below).
Both are Apache License 2.0. Their versions are recorded in the Nimbus JAR's
META-INF/maven metadata; shaded class names do not change their licenses.

com.nimbusds:content-type:2.3
Copyright 2020, Connect2id Ltd and contributors.
https://bitbucket.org/connect2id/nimbus-content-type

com.nimbusds:lang-tag:1.7
Copyright 2012-2016, Connect2id Ltd.
https://bitbucket.org/connect2id/nimbus-language-tags

com.github.stephenc.jcip:jcip-annotations:1.0-1
Copyright 2013 Stephen Connolly.
https://github.com/stephenc/jcip-annotations

net.minidev:json-smart:2.6.0
net.minidev:accessors-smart:2.6.0
Copyright 2011-2025 JSON-SMART authors.
https://github.com/netplex/json-smart-v2

BSD 3-Clause (ASM-BSD-3-Clause.txt):

org.ow2.asm:asm:9.7.1
Copyright (c) 2000-2011 INRIA, France Telecom.
https://asm.ow2.io/license.html

When upgrading runtime dependencies, update this inventory, review upstream
license/NOTICE files, and retain the notices in the distributed plugin JAR.
