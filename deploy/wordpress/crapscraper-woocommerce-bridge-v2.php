<?php
/**
 * Plugin Name: CrapScraper WooCommerce Bridge V2
 * Description: Bridge HMAC com envelope opaco para operações de adição quando o WAF bloqueia /wc/v3.
 * Version: 2.2.0
 */

if (!defined('ABSPATH')) {
    exit;
}

define('CRAPSCRAPER_STORE_BRIDGE_V2_VERSION', '2.2.0');

add_action('rest_api_init', static function (): void {
    register_rest_route('crapscraper/v2', '/bridge', [
        'methods' => 'POST',
        'callback' => 'crapscraper_store_bridge_v2_command',
        'permission_callback' => 'crapscraper_store_bridge_v2_authorize',
    ]);
});

function crapscraper_store_bridge_v2_error_data(int $status): array {
    return [
        'status' => $status,
        'bridge_version' => CRAPSCRAPER_STORE_BRIDGE_V2_VERSION,
    ];
}

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

/**
 * A chamada HMAC é uma operação administrativa do CrapScraper. O controller do
 * WooCommerce e a pilha de mídia consultam capabilities do usuário corrente;
 * como uma rota HMAC não possui cookie/login WordPress, selecionamos somente
 * durante esta request um usuário local que já tenha manage_woocommerce e
 * upload_files. Nenhuma permissão é criada ou persistida.
 */
function crapscraper_store_bridge_v2_prime_user(): bool {
    if (get_current_user_id() && current_user_can('manage_woocommerce') && current_user_can('upload_files')) {
        return true;
    }

    $users = get_users([
        'role__in' => ['administrator', 'shop_manager'],
        'number' => 20,
        'orderby' => 'ID',
        'order' => 'ASC',
    ]);
    foreach ($users as $user) {
        if (user_can($user, 'manage_woocommerce') && user_can($user, 'upload_files')) {
            wp_set_current_user((int) $user->ID);
            return true;
        }
    }
    return false;
}

function crapscraper_store_bridge_v2_authorize(WP_REST_Request $request) {
    $secret = crapscraper_store_bridge_v2_secret();
    if (strlen($secret) < 24) {
        return new WP_Error(
            'crapscraper_bridge_secret_missing',
            'Segredo HMAC do CrapScraper não configurado.',
            crapscraper_store_bridge_v2_error_data(503)
        );
    }

    $envelope = crapscraper_store_bridge_v2_envelope($request);
    if ($envelope['timestamp'] === '' || !ctype_digit($envelope['timestamp']) || $envelope['signature'] === '' || $envelope['encoded'] === '') {
        return new WP_Error(
            'crapscraper_bridge_signature_missing',
            'Assinatura CrapScraper ausente.',
            crapscraper_store_bridge_v2_error_data(403)
        );
    }
    if (abs(time() - (int) $envelope['timestamp']) > 300) {
        return new WP_Error(
            'crapscraper_bridge_signature_expired',
            'Assinatura CrapScraper expirada.',
            crapscraper_store_bridge_v2_error_data(403)
        );
    }

    $expected = hash_hmac('sha256', $envelope['timestamp'] . "\n" . $envelope['encoded'], $secret);
    if (!hash_equals($expected, $envelope['signature'])) {
        return new WP_Error(
            'crapscraper_bridge_signature_invalid',
            'Assinatura CrapScraper inválida.',
            crapscraper_store_bridge_v2_error_data(403)
        );
    }

    $decoded = base64_decode($envelope['encoded'], true);
    if ($decoded === false || strlen($decoded) > 1048576) {
        return new WP_Error(
            'crapscraper_bridge_payload_invalid',
            'Envelope CrapScraper inválido.',
            crapscraper_store_bridge_v2_error_data(400)
        );
    }
    $command = json_decode($decoded, true);
    if (!is_array($command)) {
        return new WP_Error(
            'crapscraper_bridge_payload_invalid',
            'Comando CrapScraper inválido.',
            crapscraper_store_bridge_v2_error_data(400)
        );
    }

    if (!crapscraper_store_bridge_v2_prime_user()) {
        return new WP_Error(
            'crapscraper_bridge_operator_missing',
            'Nenhum usuário WordPress com manage_woocommerce e upload_files foi encontrado para executar o bridge.',
            crapscraper_store_bridge_v2_error_data(503)
        );
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
            'bridge_version' => CRAPSCRAPER_STORE_BRIDGE_V2_VERSION,
            'message' => $result->get_error_message(),
            'code' => $result->get_error_code(),
            'data' => is_array($data) ? $data : [],
        ], $status);
    }

    $response = rest_ensure_response($result);
    $status = method_exists($response, 'get_status') ? (int) $response->get_status() : 200;
    $data = method_exists($response, 'get_data') ? $response->get_data() : $result;
    if ($status >= 400) {
        return new WP_REST_Response([
            'ok' => false,
            'bridge_version' => CRAPSCRAPER_STORE_BRIDGE_V2_VERSION,
            'message' => is_array($data) ? (string) ($data['message'] ?? 'Falha WooCommerce.') : 'Falha WooCommerce.',
            'data' => $data,
        ], $status);
    }
    return new WP_REST_Response([
        'ok' => true,
        'bridge_version' => CRAPSCRAPER_STORE_BRIDGE_V2_VERSION,
        'data' => $data,
    ], 200);
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

function crapscraper_store_bridge_v2_term_data(WP_Term $term): array {
    return [
        'id' => (int) $term->term_id,
        'name' => (string) $term->name,
        'slug' => (string) $term->slug,
        'parent' => (int) $term->parent,
    ];
}

/**
 * Resolve taxonomias diretamente no WordPress. Isso evita dois problemas vistos
 * em produção: o WAF bloqueando /wc/v3/products/categories e o controller REST
 * tentando recriar um termo cujo nome já existe em outro ramo da hierarquia.
 */
function crapscraper_store_bridge_v2_taxonomy(string $method, string $path, array $params, array $body) {
    $taxonomy = $path === '/products/categories' ? 'product_cat' : 'product_tag';
    $limit = max(1, min(100, (int) ($params['per_page'] ?? 100)));
    $slug = sanitize_title((string) ($params['slug'] ?? ''));

    if ($method === 'GET') {
        $args = [
            'taxonomy' => $taxonomy,
            'hide_empty' => false,
            'number' => $limit,
        ];
        if ($slug !== '') {
            $args['slug'] = $slug;
        }
        $terms = get_terms($args);
        if (is_wp_error($terms)) {
            return crapscraper_store_bridge_v2_response($terms);
        }
        return new WP_REST_Response([
            'ok' => true,
            'bridge_version' => CRAPSCRAPER_STORE_BRIDGE_V2_VERSION,
            'data' => array_map('crapscraper_store_bridge_v2_term_data', $terms),
        ], 200);
    }

    if ($method !== 'POST') {
        return new WP_REST_Response([
            'ok' => false,
            'bridge_version' => CRAPSCRAPER_STORE_BRIDGE_V2_VERSION,
            'message' => 'Método inválido para taxonomia.',
        ], 405);
    }

    $name = trim((string) ($body['name'] ?? ''));
    if ($name === '') {
        return new WP_REST_Response([
            'ok' => false,
            'bridge_version' => CRAPSCRAPER_STORE_BRIDGE_V2_VERSION,
            'message' => 'Nome da taxonomia vazio.',
        ], 400);
    }
    $wanted_slug = sanitize_title((string) ($body['slug'] ?? $name));

    $existing = get_terms([
        'taxonomy' => $taxonomy,
        'hide_empty' => false,
        'name' => $name,
        'number' => 1,
    ]);
    if (!is_wp_error($existing) && $existing) {
        return new WP_REST_Response([
            'ok' => true,
            'bridge_version' => CRAPSCRAPER_STORE_BRIDGE_V2_VERSION,
            'data' => crapscraper_store_bridge_v2_term_data($existing[0]),
        ], 200);
    }
    if ($wanted_slug !== '') {
        $existing = get_terms([
            'taxonomy' => $taxonomy,
            'hide_empty' => false,
            'slug' => $wanted_slug,
            'number' => 1,
        ]);
        if (!is_wp_error($existing) && $existing) {
            return new WP_REST_Response([
                'ok' => true,
                'bridge_version' => CRAPSCRAPER_STORE_BRIDGE_V2_VERSION,
                'data' => crapscraper_store_bridge_v2_term_data($existing[0]),
            ], 200);
        }
    }

    $parent = $taxonomy === 'product_cat' ? max(0, (int) ($body['parent'] ?? 0)) : 0;
    $created = wp_insert_term($name, $taxonomy, [
        'slug' => $wanted_slug,
        'parent' => $parent,
    ]);
    if (is_wp_error($created)) {
        if ($created->get_error_code() === 'term_exists') {
            $term_id = (int) $created->get_error_data('term_exists');
            $term = $term_id ? get_term($term_id, $taxonomy) : null;
            if ($term instanceof WP_Term) {
                return new WP_REST_Response([
                    'ok' => true,
                    'bridge_version' => CRAPSCRAPER_STORE_BRIDGE_V2_VERSION,
                    'data' => crapscraper_store_bridge_v2_term_data($term),
                ], 200);
            }
        }
        return crapscraper_store_bridge_v2_response($created);
    }

    $term = get_term((int) $created['term_id'], $taxonomy);
    return new WP_REST_Response([
        'ok' => true,
        'bridge_version' => CRAPSCRAPER_STORE_BRIDGE_V2_VERSION,
        'data' => $term instanceof WP_Term ? crapscraper_store_bridge_v2_term_data($term) : ['id' => (int) $created['term_id']],
    ], 200);
}

/**
 * Lê a imagem publicada em /downloads sem depender do sideload REST do
 * WooCommerce. Tentamos primeiro o arquivo local; se o PHP não tiver acesso a
 * esse diretório externo ao public_html, usamos a própria URL pública same-host
 * como fallback. Em ambos os casos validamos os bytes reais da imagem.
 */
function crapscraper_store_bridge_v2_image_bytes(string $src) {
    $src = trim($src);
    if ($src === '') {
        return new WP_Error(
            'crapscraper_bridge_image_source_missing',
            'URL da imagem do CrapScraper está vazia.',
            crapscraper_store_bridge_v2_error_data(400)
        );
    }

    $parts = wp_parse_url($src);
    $site_host = strtolower((string) wp_parse_url(home_url('/'), PHP_URL_HOST));
    $src_host = strtolower((string) ($parts['host'] ?? ''));
    $path = rawurldecode((string) ($parts['path'] ?? ''));
    if ($site_host === '' || $src_host !== $site_host || strpos($path, '/downloads/') !== 0) {
        return new WP_Error(
            'crapscraper_bridge_image_source_forbidden',
            'A imagem do produto precisa estar no /downloads do próprio site.',
            crapscraper_store_bridge_v2_error_data(400)
        );
    }

    $filename = sanitize_file_name(basename($path));
    if ($filename === '') {
        return new WP_Error(
            'crapscraper_bridge_image_filename_invalid',
            'Nome do arquivo de imagem inválido.',
            crapscraper_store_bridge_v2_error_data(400)
        );
    }

    $bytes = '';
    $origin = '';
    $candidate = dirname(rtrim(ABSPATH, '/\\')) . '/downloads/' . $filename;
    $real = realpath($candidate);
    $root = realpath(dirname(rtrim(ABSPATH, '/\\')) . '/downloads');
    if ($real && $root && strpos($real, rtrim($root, DIRECTORY_SEPARATOR) . DIRECTORY_SEPARATOR) === 0 && is_file($real) && is_readable($real)) {
        $raw = @file_get_contents($real);
        if (is_string($raw) && $raw !== '') {
            $bytes = $raw;
            $origin = 'local';
        }
    }

    if ($bytes === '') {
        $response = wp_safe_remote_get($src, [
            'timeout' => 45,
            'redirection' => 2,
            'headers' => [
                'Accept' => 'image/avif,image/webp,image/png,image/jpeg,*/*;q=0.8',
                'User-Agent' => 'Mozilla/5.0 (compatible; CrapScraper/2.2)',
            ],
        ]);
        if (is_wp_error($response)) {
            return new WP_Error(
                'crapscraper_bridge_image_fetch_failed',
                'Não foi possível ler a imagem publicada em /downloads: ' . $response->get_error_message(),
                crapscraper_store_bridge_v2_error_data(400)
            );
        }
        $status = (int) wp_remote_retrieve_response_code($response);
        $raw = (string) wp_remote_retrieve_body($response);
        if ($status < 200 || $status >= 300 || $raw === '') {
            return new WP_Error(
                'crapscraper_bridge_image_fetch_failed',
                'A imagem publicada em /downloads não pôde ser lida pelo WordPress (HTTP ' . $status . ').',
                crapscraper_store_bridge_v2_error_data(400)
            );
        }
        $bytes = $raw;
        $origin = 'http';
    }

    if (strlen($bytes) <= 1024) {
        return new WP_Error(
            'crapscraper_bridge_image_too_small',
            'A imagem publicada pelo CrapScraper está vazia ou pequena demais.',
            crapscraper_store_bridge_v2_error_data(400)
        );
    }

    $info = @getimagesizefromstring($bytes);
    $mime = is_array($info) ? strtolower((string) ($info['mime'] ?? '')) : '';
    $allowed = ['image/png' => 'png', 'image/jpeg' => 'jpg', 'image/webp' => 'webp'];
    if (!isset($allowed[$mime])) {
        return new WP_Error(
            'crapscraper_bridge_image_type_invalid',
            'A imagem publicada pelo CrapScraper não é PNG, JPEG ou WebP válido.',
            crapscraper_store_bridge_v2_error_data(400)
        );
    }

    return [
        'bytes' => $bytes,
        'mime' => $mime,
        'extension' => $allowed[$mime],
        'filename' => $filename,
        'origin' => $origin,
    ];
}

/**
 * Converte os bytes validados da imagem em attachment diretamente na pasta de
 * uploads. Não usamos media_handle_sideload/wp_handle_sideload, portanto a
 * criação não depende da política de extensões que estava rejeitando a imagem
 * no controller REST apesar de os bytes serem válidos.
 */
function crapscraper_store_bridge_v2_local_image_id(string $src, string $title) {
    $image = crapscraper_store_bridge_v2_image_bytes($src);
    if (is_wp_error($image)) {
        return $image;
    }

    $bytes = (string) $image['bytes'];
    $mime = (string) $image['mime'];
    $extension = (string) $image['extension'];
    $filename = (string) $image['filename'];
    $origin = (string) $image['origin'];
    $hash = hash('sha256', $bytes);

    if ($hash) {
        $found = get_posts([
            'post_type' => 'attachment',
            'post_status' => 'inherit',
            'posts_per_page' => 1,
            'fields' => 'ids',
            'meta_key' => 'crapscraper_source_image_sha256',
            'meta_value' => $hash,
        ]);
        if ($found) {
            return (int) $found[0];
        }
    }

    $uploads = wp_upload_dir();
    if (!empty($uploads['error'])) {
        return new WP_Error(
            'crapscraper_bridge_upload_dir_failed',
            'WordPress não disponibilizou a pasta de uploads: ' . (string) $uploads['error'],
            crapscraper_store_bridge_v2_error_data(500)
        );
    }
    if (!wp_mkdir_p($uploads['path'])) {
        return new WP_Error(
            'crapscraper_bridge_upload_dir_failed',
            'WordPress não conseguiu criar a pasta de uploads.',
            crapscraper_store_bridge_v2_error_data(500)
        );
    }

    $base = sanitize_file_name(pathinfo($filename, PATHINFO_FILENAME));
    if ($base === '') {
        $base = 'crapscraper-product-image';
    }
    $target_name = wp_unique_filename($uploads['path'], $base . '.' . $extension);
    $target = trailingslashit($uploads['path']) . $target_name;
    $written = @file_put_contents($target, $bytes, LOCK_EX);
    if (!$written || $written !== strlen($bytes)) {
        @unlink($target);
        return new WP_Error(
            'crapscraper_bridge_image_write_failed',
            'WordPress não conseguiu gravar a imagem na Biblioteca de Mídia.',
            crapscraper_store_bridge_v2_error_data(500)
        );
    }

    $attachment_id = wp_insert_attachment([
        'post_mime_type' => $mime,
        'post_title' => sanitize_text_field($title !== '' ? $title : $base),
        'post_status' => 'inherit',
    ], $target);
    if (is_wp_error($attachment_id) || !$attachment_id) {
        @unlink($target);
        return is_wp_error($attachment_id)
            ? $attachment_id
            : new WP_Error(
                'crapscraper_bridge_attachment_failed',
                'WordPress não retornou ID ao registrar a imagem.',
                crapscraper_store_bridge_v2_error_data(500)
            );
    }

    require_once ABSPATH . 'wp-admin/includes/image.php';
    $metadata = wp_generate_attachment_metadata((int) $attachment_id, $target);
    if (is_array($metadata)) {
        wp_update_attachment_metadata((int) $attachment_id, $metadata);
    }
    if ($hash) {
        update_post_meta((int) $attachment_id, 'crapscraper_source_image_sha256', $hash);
    }
    update_post_meta((int) $attachment_id, 'crapscraper_source_image_origin', 'downloads_bridge_v2_' . $origin);
    return (int) $attachment_id;
}

function crapscraper_store_bridge_v2_prepare_product_body(array $body) {
    $images = is_array($body['images'] ?? null) ? $body['images'] : [];
    if (!$images) {
        return $body;
    }
    $title = trim((string) ($body['name'] ?? 'Produto CrapScraper'));
    foreach ($images as $index => $image) {
        if (!is_array($image) || !empty($image['id']) || empty($image['src'])) {
            continue;
        }
        $attachment_id = crapscraper_store_bridge_v2_local_image_id((string) $image['src'], $title);
        if (is_wp_error($attachment_id)) {
            return $attachment_id;
        }
        if ((int) $attachment_id <= 0) {
            return new WP_Error(
                'crapscraper_bridge_image_import_failed',
                'O bridge não conseguiu transformar a imagem publicada em attachment.',
                crapscraper_store_bridge_v2_error_data(400)
            );
        }
        $images[$index] = ['id' => (int) $attachment_id];
    }
    $body['images'] = $images;
    return $body;
}

function crapscraper_store_bridge_v2_command(WP_REST_Request $outer) {
    if (!class_exists('WooCommerce')) {
        return new WP_REST_Response([
            'ok' => false,
            'bridge_version' => CRAPSCRAPER_STORE_BRIDGE_V2_VERSION,
            'message' => 'WooCommerce não está ativo.',
        ], 503);
    }

    $payload = $outer->get_param('_crapscraper_bridge_command');
    if (!is_array($payload)) {
        return new WP_REST_Response([
            'ok' => false,
            'bridge_version' => CRAPSCRAPER_STORE_BRIDGE_V2_VERSION,
            'message' => 'Comando CrapScraper ausente.',
        ], 400);
    }

    $method = strtoupper(trim((string) ($payload['method'] ?? '')));
    $path = trim((string) ($payload['path'] ?? ''));
    $params = is_array($payload['params'] ?? null) ? $payload['params'] : [];
    $body = is_array($payload['json'] ?? null) ? $payload['json'] : [];

    if (!in_array($method, ['GET', 'POST', 'PUT'], true)) {
        return new WP_REST_Response([
            'ok' => false,
            'bridge_version' => CRAPSCRAPER_STORE_BRIDGE_V2_VERSION,
            'message' => 'Método não permitido no bridge.',
        ], 405);
    }

    try {
        if ($path === '/products/categories' || $path === '/products/tags') {
            return crapscraper_store_bridge_v2_taxonomy($method, $path, $params, $body);
        }

        if ($path === '/products') {
            if (!class_exists('WC_REST_Products_Controller')) {
                return new WP_REST_Response([
                    'ok' => false,
                    'bridge_version' => CRAPSCRAPER_STORE_BRIDGE_V2_VERSION,
                    'message' => 'Controller de produtos WooCommerce indisponível.',
                ], 503);
            }
            $controller = new WC_REST_Products_Controller();
            if ($method === 'POST') {
                $prepared = crapscraper_store_bridge_v2_prepare_product_body($body);
                if (is_wp_error($prepared)) {
                    return crapscraper_store_bridge_v2_response($prepared);
                }
                $body = $prepared;
            }
            $request = crapscraper_store_bridge_v2_request($method, $params, $body);
            if ($method === 'GET') {
                return crapscraper_store_bridge_v2_response($controller->get_items($request));
            }
            if ($method === 'POST') {
                return crapscraper_store_bridge_v2_response($controller->create_item($request));
            }
            return new WP_REST_Response([
                'ok' => false,
                'bridge_version' => CRAPSCRAPER_STORE_BRIDGE_V2_VERSION,
                'message' => 'Método inválido para produtos.',
            ], 405);
        }

        if (preg_match('~^/products/(\d+)$~', $path, $matches)) {
            if (!class_exists('WC_REST_Products_Controller')) {
                return new WP_REST_Response([
                    'ok' => false,
                    'bridge_version' => CRAPSCRAPER_STORE_BRIDGE_V2_VERSION,
                    'message' => 'Controller de produtos WooCommerce indisponível.',
                ], 503);
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
            return new WP_REST_Response([
                'ok' => false,
                'bridge_version' => CRAPSCRAPER_STORE_BRIDGE_V2_VERSION,
                'message' => 'Método inválido para produto individual.',
            ], 405);
        }

        if (preg_match('~^/products/(\d+)/variations$~', $path, $matches)) {
            if (!class_exists('WC_REST_Product_Variations_Controller')) {
                return new WP_REST_Response([
                    'ok' => false,
                    'bridge_version' => CRAPSCRAPER_STORE_BRIDGE_V2_VERSION,
                    'message' => 'Controller de variações WooCommerce indisponível.',
                ], 503);
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
            return new WP_REST_Response([
                'ok' => false,
                'bridge_version' => CRAPSCRAPER_STORE_BRIDGE_V2_VERSION,
                'message' => 'Método inválido para variações.',
            ], 405);
        }
    } catch (Throwable $error) {
        return new WP_REST_Response([
            'ok' => false,
            'bridge_version' => CRAPSCRAPER_STORE_BRIDGE_V2_VERSION,
            'message' => 'Falha interna do bridge WooCommerce: ' . $error->getMessage(),
        ], 500);
    }

    return new WP_REST_Response([
        'ok' => false,
        'bridge_version' => CRAPSCRAPER_STORE_BRIDGE_V2_VERSION,
        'message' => 'Caminho não permitido no bridge.',
    ], 404);
}
