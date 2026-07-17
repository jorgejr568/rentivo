/**
 * WebAuthn browser API helpers for passkey registration and authentication.
 */

function bufferToBase64url(buffer) {
    var bytes = new Uint8Array(buffer);
    var str = '';
    for (var i = 0; i < bytes.length; i++) {
        str += String.fromCharCode(bytes[i]);
    }
    return btoa(str).replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
}

function base64urlToBuffer(base64url) {
    var base64 = base64url.replace(/-/g, '+').replace(/_/g, '/');
    while (base64.length % 4) {
        base64 += '=';
    }
    var binary = atob(base64);
    var bytes = new Uint8Array(binary.length);
    for (var i = 0; i < binary.length; i++) {
        bytes[i] = binary.charCodeAt(i);
    }
    return bytes.buffer;
}

function webauthnRegister(beginUrl, completeUrl, name) {
    fetch(beginUrl, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name: name})
    })
    .then(function(resp) { return resp.json(); })
    .then(function(options) {
        if (options.error) {
            alert(options.error);
            return Promise.reject(options.error);
        }

        // Decode challenge and user.id from base64url
        options.challenge = base64urlToBuffer(options.challenge);
        options.user.id = base64urlToBuffer(options.user.id);

        if (options.excludeCredentials) {
            options.excludeCredentials = options.excludeCredentials.map(function(cred) {
                cred.id = base64urlToBuffer(cred.id);
                return cred;
            });
        }

        return navigator.credentials.create({publicKey: options});
    })
    .then(function(credential) {
        if (!credential) return;

        var body = {
            id: credential.id,
            rawId: bufferToBase64url(credential.rawId),
            type: credential.type,
            name: name,
            response: {
                attestationObject: bufferToBase64url(credential.response.attestationObject),
                clientDataJSON: bufferToBase64url(credential.response.clientDataJSON)
            }
        };

        if (credential.response.getTransports) {
            body.response.transports = credential.response.getTransports();
        }

        return fetch(completeUrl, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body)
        });
    })
    .then(function(resp) {
        if (!resp) return;
        return resp.json();
    })
    .then(function(result) {
        if (!result) return;
        if (result.error) {
            alert(result.error);
        } else {
            window.location.reload();
        }
    })
    .catch(function(err) {
        if (err.name !== 'NotAllowedError') {
            console.error('WebAuthn registration error:', err);
            alert('Erro ao registrar passkey. Tente novamente.');
        }
    });
}

function webauthnAuthenticate(beginUrl, completeUrl) {
    fetch(beginUrl, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'}
    })
    .then(function(resp) { return resp.json(); })
    .then(function(options) {
        if (options.error) {
            alert(options.error);
            return Promise.reject(options.error);
        }

        options.challenge = base64urlToBuffer(options.challenge);

        if (options.allowCredentials) {
            options.allowCredentials = options.allowCredentials.map(function(cred) {
                cred.id = base64urlToBuffer(cred.id);
                return cred;
            });
        }

        return navigator.credentials.get({publicKey: options});
    })
    .then(function(assertion) {
        if (!assertion) return;

        var body = {
            id: assertion.id,
            rawId: bufferToBase64url(assertion.rawId),
            type: assertion.type,
            response: {
                authenticatorData: bufferToBase64url(assertion.response.authenticatorData),
                clientDataJSON: bufferToBase64url(assertion.response.clientDataJSON),
                signature: bufferToBase64url(assertion.response.signature)
            }
        };

        if (assertion.response.userHandle) {
            body.response.userHandle = bufferToBase64url(assertion.response.userHandle);
        }

        return fetch(completeUrl, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body)
        });
    })
    .then(function(resp) {
        if (!resp) return;
        return resp.json();
    })
    .then(function(result) {
        if (!result) return;
        if (result.error) {
            alert(result.error);
        } else if (result.redirect) {
            window.location.href = result.redirect;
        } else {
            window.location.reload();
        }
    })
    .catch(function(err) {
        if (err.name !== 'NotAllowedError') {
            console.error('WebAuthn authentication error:', err);
            alert('Erro na autenticação com passkey. Tente novamente.');
        }
    });
}
