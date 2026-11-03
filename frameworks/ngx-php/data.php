<?php

// benchmark data
define('JSON_DATA', json_decode(file_get_contents('/data/dataset.json'), true));
//define('LARGE_JSON', largeJson());

//createGzFiles();

// const MIME = [
//     'css'   => "text/css",
//     'js'    => "application/javascript",
//     'html'  => "text/html",
//     'woff2' => "font/woff2",
//     'svg'   => "image/svg+xml",
//     'webp'  => "image/webp",
//     'json'  => "application/json"
// ];
//define('STATIC_FILES', loadStaticFiles());

// function largeJson()
// {
//     $data = json_decode(file_get_contents('/data/dataset-large.json'), true);
//     foreach ($data as &$item) {
//         $item['total'] = $item['price'] * $item['quantity'];
//     }

//     return json_encode(['items' => $data, 'count' => count($data)], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
// }

// function loadStaticFiles() 
// {
//     $files = [];
//     $dir = new DirectoryIterator('/data/static');
//     foreach ($dir as $fileinfo) {
//         if (!$fileinfo->isDot()) {
//             $files['/static/' . $fileinfo->getFilename()] = [
//                 file_get_contents($fileinfo->getPathname()),
//                 MIME[pathinfo($fileinfo->getFilename(), PATHINFO_EXTENSION)] ?? 'application/octet-stream'
//             ];
//         }
//     }
//     return $files;
// }

// function createGzFiles()
// {
//     $files = glob('/data/static/*..{js,css,html,svg}', GLOB_BRACE);
//     foreach ($files as $file) {
//         file_put_contents($file . '.gz', gzencode(file_get_contents($file), 1));
//     }
// }
