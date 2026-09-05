<?php
/**
 * Plugin Name: CrapScraper WooCommerce Bridge V2
 * Description: Bridge HMAC com envelope opaco para operações de adição quando o WAF bloqueia /wc/v3.
 * Version: 2.0.0
 */

if (!defined('ABSPATH')) {
    exit;
}

add_action('rest_api_init', static function (): void {
    register_rest_route('crapscraper/v2', '/bridge', [
        'methods' => 'POST',
        'callback' => 'crapscraper_store_bridge_v2_command',
        'permission_callback' => 'crapscraper_store_bridge_v2_authorize',
    ]);
});

function crapscraper_store_bridge_v2_secret(): string {
    if (defined('CRAPSCRAPER_MANUAL_SECRET')) {
        return trim((string) CRAPSCRAPER_MANUAL_SECRET);
    }
    return trim((string) get_option('crapscraper_manual_update_secret', ''));
}

function crapscraper_store_bridge_v2_envelope(WP_REST_Request $request): array {
    $payload = $request->get_json_params();
    if (!is_array($payload)) {
        $payload = [];
    }
    return [
        'timestamp' => trim((string) ($payload['t'] ?? '')),
        'signature' => strtolower(trim((string) ($payload['s'] ?? ''))),
        'encoded' => trim((string) ($payload['p'] ?? '')),
    ];
}

function crapscraper_store_bridge_v2_authorize(WP_REST_Request $request) {
    $secret = crapscraper_store_bridge_v2_secret();
    if (strlen($secret) < 24) {
        return new WP_Error('crapscraper_bridge_secret_missing', 'Segredo HMAC do CrapScraper não configurado.', ['status' => 503]);
    }

    $envelope = crapscraper_store_bridge_v2_envelope($request);
    if ($envelope['timestamp'] === '' || !ctype_digit($envelope['timestamp']) || $envelope['signature'] === '' || $envelope['encoded'] === '') {
        return new WP_Error('crapscraper_bridge_signature_missing', 'Assinatura CrapScraper ausente.', ['status' => 403]);
    }
    if (abs(time() - (int) $envelope['timestamp']) > 300) {
        return new WP_Error('crapscraper_bridge_signature_expired', 'Assinatura CrapScraper expirada.', ['status' => 403]);
    }

    $expected = hash_hmac('sha256', $envelope['timestamp'] . "\n" . $envelope['encoded'], $secret);
    if (!hash_equals($expected, $envelope['signature'])) {
        return new WP_Error('crapscraper_bridge_signature_invalid', 'Assinatura CrapScraper inválida.', ['status' => 403]);
    }

    $decoded = base64_decode($envelope['encoded'], true);
    if ($decoded === false || strlen($decoded) > 1048576) {
        return new WP_Error('crapscraper_bridge_payload_invalid', 'Envelope CrapScraper inválido.', ['status' => 400]);
    }
    $command = json_decode($decoded, true);
    if (!is_array($command)) {
        return new WP_Error('crapscraper_bridge_payload_invalid', 'Comando CrapScraper inválido.', ['status' => 400]);
    }
    $request->set_param('_crapscraper_bridge_command', $command);
    return true;
}

function crapscraper_store_bridge_v2_response($result) {
    if (is_wp_error($result)) {
        $data = $result->get_error_data();
        $status = is_array($data) && !empty($data['status']) ? (int) $data['status'] : 400;
        return new WP_REST_Response([
            'ok' => false,
            'message' => $result->get_error_message(),
            'code' => $result->get_error_code(),
        ], $status);
    }

    $response = rest_ensure_response($result);
    $status = method_exists($response, 'get_status') ? (int) $response->get_status() : 200;
    $data = method_exists($response, 'get_data') ? $response->get_data() : $result;
    if ($status >= 400) {
        return new WP_REST_Response([
            'ok' => false,
            'message' => is_array($data) ? (string) ($data['message'] ?? 'Falha WooCommerce.') : 'Falha WooCommerce.',
            'data' => $data,
        ], $status);
    }
    return new WP_REST_Response(['ok' => true, 'data' => $data], 200);
}

function crapscraper_store_bridge_v2_request(string $method, array $params, array $body): WP_REST_Request {
    $request = new WP_REST_Request($method, '/crapscraper-internal');
    if ($params) {
        $request->set_query_params($params);
    }
    if ($body) {
        $request->set_body_params($body);
    }
    return $request;
}

function crapscraper_store_bridge_v2_command(WP_REST_Request $outer) {
    if (!class_exists('WooCommerce')) {
        return new WP_REST_Response(['ok' => false, 'message' => 'WooCommerce não está ativo.'], 503);
    }

    $payload = $outer->get_param('_crapscraper_bridge_command');
    if (!is_array($payload)) {
        return new WP_REST_Response(['ok' => false, 'message' => 'Comando CrapScraper ausente.'], 400);
    }

    $method = strtoupper(trim((string) ($payload['method'] ?? '')));
    $path = trim((string) ($payload['path'] ?? ''));
    $params = is_array($payload['params'] ?? null) ? $payload['params'] : [];
    $body = is_array($payload['json'] ?? null) ? $payload['json'] : [];

    if (!in_array($method, ['GET', 'POST', 'PUT'], true)) {
        return new WP_REST_Response(['ok' => false, 'message' => 'Método não permitido no bridge.'], 405);
    }

    try {
        if ($path === '/products') {
            if (!class_exists('WC_REST_Products_Controller')) {
                return new WP_REST_Response(['ok' => false, 'message' => 'Controller de produtos WooCommerce indisponível.'], 503);
            }
            $controller = new WC_REST_Products_Controller();
            $request = crapscraper_store_bridge_v2_request($method, $params, $body);
            if ($method === 'GET') {
                return crapscraper_store_bridge_v2_response($controller->get_items($request));
            }
            if ($method === 'POST') {
                return crapscraper_store_bridge_v2_response($controller->create_item($request));
            }
            return new WP_REST_Response(['ok' => false, 'message' => 'Método inválido para produtos.'], 405);
        }

        if (preg_match('~^/products/(\d+)$~', $path, $matches)) {
            if (!class_exists('WC_REST_Products_Controller')) {
                return new WP_REST_Response(['ok' => false, 'message' => 'Controller de produtos WooCommerce indisponível.'], 503);
            }
            $controller = new WC_REST_Products_Controller();
            $request = crapscraper_store_bridge_v2_request($method, $params, $body);
            $request->set_param('id', (int) $matches[1]);
            if ($method === 'GET') {
                return crapscraper_store_bridge_v2_response($controller->get_item($request));
            }
            if ($method === 'PUT') {
                return crapscraper_store_bridge_v2_response($controller->update_item($request));
            }
            return new WP_REST_Response(['ok' => false, 'message' => 'Método inválido para produto individual.'], 405);
        }

        if (preg_match('~^/products/(\d+)/variations$~', $path, $matches)) {
            if (!class_exists('WC_REST_Product_Variations_Controller')) {
                return new WP_REST_Response(['ok' => false, 'message' => 'Controller de variações WooCommerce indisponível.'], 503);
            }
            $controller = new WC_REST_Product_Variations_Controller();
            $request = crapscraper_store_bridge_v2_request($method, $params, $body);
            $request->set_param('product_id', (int) $matches[1]);
            if ($method === 'GET') {
                return crapscraper_store_bridge_v2_response($controller->get_items($request));
            }
            if ($method === 'POST') {
                return crapscraper_store_bridge_v2_response($controller->create_item($request));
            }
            return new WP_REST_Response(['ok' => false, 'message' => 'Método inválido para variações.'], 405);
        }

        if ($path === '/products/categories' || $path === '/products/tags') {
            $is_category = $path === '/products/categories';
            $class = $is_category ? 'WC_REST_Product_Categories_Controller' : 'WC_REST_Product_Tags_Controller';
            if (!class_exists($class)) {
                return new WP_REST_Response(['ok' => false, 'message' => 'Controller de taxonomia WooCommerce indisponível.'], 503);
            }
            $controller = new $class();
            $request = crapscraper_store_bridge_v2_request($method, $params, $body);
            if ($method === 'GET') {
                return crapscraper_store_bridge_v2_response($controller->get_items($request));
            }
            if ($method === 'POST') {
                return crapscraper_store_bridge_v2_response($controller->create_item($request));
            }
            return new WP_REST_Response(['ok' => false, 'message' => 'Método inválido para taxonomia.'], 405);
        }
    } catch (Throwable $error) {
        return new WP_REST_Response([
            'ok' => false,
            'message' => 'Falha interna do bridge WooCommerce: ' . $error->getMessage(),
        ], 500);
    }

    return new WP_REST_Response(['ok' => false, 'message' => 'Caminho não permitido no bridge.'], 404);
}
