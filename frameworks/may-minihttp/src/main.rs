#[global_allocator]
static GLOBAL: mimalloc::MiMalloc = mimalloc::MiMalloc;

use may::net::TcpListener;
use std::io::{self, Read, Write};

const BUF_SIZE: usize = 4096;
const MAX_HEADERS: usize = 16;

fn parse_query_params(path: &[u8]) -> i64 {
    let qs = match memchr(b'?', path) {
        Some(pos) => &path[pos + 1..],
        None => return 0,
    };
    let mut sum: i64 = 0;
    for pair in qs.split(|&b| b == b'&') {
        if let Some(pos) = memchr(b'=', pair) {
            if let Ok(s) = std::str::from_utf8(&pair[pos + 1..]) {
                if let Ok(n) = s.parse::<i64>() {
                    sum += n;
                }
            }
        }
    }
    sum
}

fn memchr(needle: u8, haystack: &[u8]) -> Option<usize> {
    haystack.iter().position(|&b| b == needle)
}

fn route_path(path: &[u8]) -> &[u8] {
    match memchr(b'?', path) {
        Some(pos) => &path[..pos],
        None => path,
    }
}

/// Read body with Content-Length
fn read_body_content_length(
    buf: &[u8],
    stream: &mut may::net::TcpStream,
    content_length: usize,
) -> io::Result<Vec<u8>> {
    let mut body = Vec::with_capacity(content_length);
    let take = content_length.min(buf.len());
    body.extend_from_slice(&buf[..take]);
    let mut remaining = content_length - take;
    while remaining > 0 {
        let mut tmp = [0u8; 4096];
        let n = stream.read(&mut tmp)?;
        if n == 0 {
            break;
        }
        let take = remaining.min(n);
        body.extend_from_slice(&tmp[..take]);
        remaining -= take;
    }
    Ok(body)
}

/// Read chunked transfer-encoded body
fn read_body_chunked(
    buf: &[u8],
    stream: &mut may::net::TcpStream,
) -> io::Result<Vec<u8>> {
    let mut body = Vec::new();
    let mut data = buf.to_vec();

    loop {
        // Find chunk size line
        loop {
            if let Some(pos) = find_crlf(&data) {
                let size_str = std::str::from_utf8(&data[..pos]).unwrap_or("0").trim();
                let chunk_size = usize::from_str_radix(size_str, 16).unwrap_or(0);
                data.drain(..pos + 2); // consume size line + CRLF

                if chunk_size == 0 {
                    // Terminal chunk — consume trailing CRLF
                    return Ok(body);
                }

                // Read chunk_size bytes + trailing CRLF
                while data.len() < chunk_size + 2 {
                    let mut tmp = [0u8; 4096];
                    let n = stream.read(&mut tmp)?;
                    if n == 0 {
                        return Ok(body);
                    }
                    data.extend_from_slice(&tmp[..n]);
                }
                body.extend_from_slice(&data[..chunk_size]);
                data.drain(..chunk_size + 2); // consume chunk data + CRLF
                break; // parse next chunk
            }

            // Need more data for chunk size line
            let mut tmp = [0u8; 4096];
            let n = stream.read(&mut tmp)?;
            if n == 0 {
                return Ok(body);
            }
            data.extend_from_slice(&tmp[..n]);
        }
    }
}

fn find_crlf(data: &[u8]) -> Option<usize> {
    for i in 0..data.len().saturating_sub(1) {
        if data[i] == b'\r' && data[i + 1] == b'\n' {
            return Some(i);
        }
    }
    None
}

fn handle_connection(mut stream: may::net::TcpStream) -> io::Result<()> {
    let mut buf = vec![0u8; BUF_SIZE];
    let mut filled = 0;

    loop {
        // Read more data
        if filled == buf.len() {
            buf.resize(buf.len() * 2, 0);
        }
        let n = stream.read(&mut buf[filled..])?;
        if n == 0 {
            return Ok(());
        }
        filled += n;

        // Try to parse request
        loop {
            let mut headers = [httparse::EMPTY_HEADER; MAX_HEADERS];
            let mut req = httparse::Request::new(&mut headers);
            let status = match req.parse(&buf[..filled]) {
                Ok(s) => s,
                Err(_) => return Ok(()),
            };

            let header_len = match status {
                httparse::Status::Complete(len) => len,
                httparse::Status::Partial => break, // need more data
            };

            let method = req.method.unwrap_or("GET");
            let path = req.path.unwrap_or("/").as_bytes();
            let route = route_path(path);

            // Find content-length and transfer-encoding
            let mut content_length: Option<usize> = None;
            let mut is_chunked = false;
            for h in req.headers.iter() {
                if h.name.eq_ignore_ascii_case("content-length") {
                    content_length = std::str::from_utf8(h.value)
                        .ok()
                        .and_then(|s| s.trim().parse().ok());
                } else if h.name.eq_ignore_ascii_case("transfer-encoding") {
                    if let Ok(v) = std::str::from_utf8(h.value) {
                        is_chunked = v.to_ascii_lowercase().contains("chunked");
                    }
                }
            }

            // Body data starts after headers
            let body_start = &buf[header_len..filled];

            // Read body if POST
            let body_bytes: Option<Vec<u8>> = if method == "POST" {
                if is_chunked {
                    Some(read_body_chunked(body_start, &mut stream)?)
                } else if let Some(cl) = content_length {
                    let body = read_body_content_length(body_start, &mut stream, cl)?;
                    Some(body)
                } else {
                    None
                }
            } else {
                None
            };

            // Compute how much of buf was consumed (headers + body from buf)
            let body_consumed = if method == "POST" {
                if is_chunked {
                    // chunked reader consumed from body_start + stream
                    body_start.len()
                } else if let Some(cl) = content_length {
                    cl.min(body_start.len())
                } else {
                    0
                }
            } else {
                0
            };
            let total_consumed = header_len + body_consumed;

            // Route and generate response
            let response = match route {
                b"/baseline11" => {
                    let mut sum = parse_query_params(path);
                    if let Some(ref body) = body_bytes {
                        if let Ok(s) = std::str::from_utf8(body) {
                            if let Ok(n) = s.trim().parse::<i64>() {
                                sum += n;
                            }
                        }
                    }
                    let body_str = sum.to_string();
                    format!(
                        "HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: {}\r\n\r\n{}",
                        body_str.len(),
                        body_str
                    )
                }
                b"/pipeline" => {
                    "HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 2\r\n\r\nok"
                        .to_string()
                }
                _ => {
                    "HTTP/1.1 404 Not Found\r\nContent-Type: text/plain\r\nContent-Length: 9\r\n\r\nnot found"
                        .to_string()
                }
            };

            stream.write_all(response.as_bytes())?;

            // Shift remaining data
            if total_consumed < filled {
                buf.copy_within(total_consumed..filled, 0);
                filled -= total_consumed;
            } else {
                filled = 0;
            }

            if filled == 0 {
                break;
            }
        }
    }
}

fn main() {
    let cpus = num_cpus::get();
    may::config().set_workers(cpus);

    let listener = TcpListener::bind("0.0.0.0:8080").unwrap();
    eprintln!("may-minihttp listening on :8080 with {} workers", cpus);

    while let Ok((stream, _)) = listener.accept() {
        unsafe {
            may::coroutine::spawn(move || {
                let _ = handle_connection(stream);
            });
        }
    }
}
