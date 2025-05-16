# extract_features.py

import re
import pandas as pd
from bs4 import BeautifulSoup, Comment
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from pathlib import Path

# Ensure output directory exists
Path('features').mkdir(parents=True, exist_ok=True)


class Extractor:
    def __init__(self):
        pass

    def n_ext_links(self, links, hostname):
        external = 0
        for link in links:
            try:
                if link and re.match(r"^https?://", link):
                    lh = urlparse(link).hostname or ""
                    if not lh.endswith(hostname.replace("www.", "")):
                        external += 1
            except Exception:
                continue
        return external

    def general_f(self, soup, hostname):
        n_script  = len(soup.find_all('script'))
        n_style   = len(soup.find_all('style'))
        n_link    = len(soup.find_all('link'))
        n_comment = len(soup.find_all(string=lambda s: isinstance(s, Comment)))
        html_len  = len(str(soup))

        # body descendants
        body = soup.body
        body_desc = [tag.name for tag in body.find_all()] if body else []
        diff_body = len(set(body_desc))
        n_body = len(soup.find_all('body'))
        n_head = len(soup.find_all('head'))

        title_tag = int(bool(soup.find('title') and soup.head and soup.head.find('title')))
        brand = hostname.replace("www.", "").split('.')[0].lower()
        title = soup.find('title')
        title_brand = int(bool(title and brand and brand in title.get_text(strip=True).lower()))

        return {
            'html_length': html_len,
            'n_script_tag': n_script,
            'n_style_tag': n_style,
            'n_link_tag':  n_link,
            'n_comment_tag': n_comment,
            'diff_body_children': diff_body,
            'n_body_tag': n_body,
            'n_head_tag': n_head,
            'title_tag': title_tag,
            'title_url_brand': title_brand
        }

    def a_tag(self, soup, hostname):
        links = [a['href'].strip() for a in soup.find_all('a', href=True) if a.text]
        n = len(links)
        nullp = (links.count("") + links.count("#")) / n if n else 0
        ext = self.n_ext_links(links, hostname) / n if n else 0
        return {
            'n_hyperlinks': n,
            'nullpointers_ratio': round(nullp, 2),
            'external_ratio': round(ext, 2)
        }

    def form_tag(self, soup, hostname):
        forms = soup.find_all('form')
        totals = len(forms)
        n_ext = n_abn = n_int = 0
        form_input_b = int(bool(soup.find('input') and soup.find('input').find_parent('form')))
        for f in forms:
            action = f.get('action', '').strip()
            if not action or action in ('#', 'about:blank'):
                n_abn += 1
            elif self.n_ext_links([action], hostname) == 1:
                n_ext += 1
            else:
                n_int += 1
        return {
            'form_input_b': form_input_b,
            'int_form_act_ratio': round(n_int/totals, 2) if totals else 0,
            'abn_form_act_ratio': round(n_abn/totals, 2) if totals else 0,
            'ext_form_act_ratio': round(n_ext/totals, 2) if totals else 0
        }

    def ext_resource(self, soup, hostname):
        imgs    = [img['src'].strip() for img in soup.find_all('img', src=True)]
        scripts = [s['src'].strip() for s in soup.find_all('script', src=True)]
        links   = [l['href'].strip() for l in soup.find_all('link', href=True)]
        total = len(imgs) + len(scripts) + len(links)
        ext = (self.n_ext_links(imgs, hostname)
               + self.n_ext_links(scripts, hostname)
               + self.n_ext_links(links, hostname))
        return round(ext/total, 2) if total else 0

    def favicon_feature(self, soup, url_t, hostname):
        for rel in ('shortcut icon', 'icon'):
            link = soup.find('link', rel=rel)
            if link and link.get('href'):
                if self.n_ext_links([link['href']], hostname) == 0:
                    return 1
        parsed = urlparse(url_t)
        scheme = parsed.scheme or 'https'
        host = parsed.hostname
        if not host:
            return 0
        ico = f"{scheme}://{host}/favicon.ico"
        try:
            req = Request(ico, headers={'User-Agent':'Mozilla/5.0'})
            resp = urlopen(req, timeout=10)
            if resp.read():
                return 1
        except Exception:
            pass
        return 0

    def disabled_status(self, soup, hostname):
        cnt = len(soup.find_all('div', style='visibility: hidden'))
        cnt += len(soup.find_all('div', style='display: none'))
        cnt += len(soup.find_all('button', disabled=True))
        cnt += len(soup.find_all('input', disabled=True))
        cnt += len(soup.find_all('input', type='hidden'))
        return cnt


def extra_content_features(soup: BeautifulSoup):
    return {
        'n_img_tag':      len(soup.find_all('img')),
        'n_meta_refresh': len(soup.find_all('meta', attrs={'http-equiv':'refresh'}))
    }


def build_mapping(csv_path, status_filter=None, id_col=None):
    df = pd.read_csv(csv_path)
    if status_filter:
        col, val = status_filter
        df = df[df[col] == val]
    if id_col and id_col in df.columns:
        # use CSV's ID column
        mapping = { str(row[id_col]): row['url'] for _, row in df.iterrows() }
    else:
        # fallback to DataFrame index
        mapping = { str(idx): row['url'] for idx, row in df.iterrows() }
    return mapping


def process_set(mapping, html_dir, output_csv, label):
    extractor = Extractor()
    html_dir = Path(html_dir)
    out_path = Path(output_csv)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    first = True
    with out_path.open('w', encoding='utf-8', newline='') as out:
        for idx, url in mapping.items():
            file_path = html_dir / f"{idx}.html"
            if not file_path.exists() or file_path.stat().st_size < 20:
                continue
            try:
                text = file_path.read_text(encoding='utf-8', errors='ignore').strip()
            except OSError:
                continue
            if not text:
                continue

            soup = BeautifulSoup(text, 'html.parser')
            hostname = urlparse(url).hostname or ''

            feats = {}
            feats.update(extractor.a_tag(soup, hostname))
            feats.update(extractor.form_tag(soup, hostname))
            feats.update(extractor.general_f(soup, hostname))
            feats['ext_res_ratio']           = extractor.ext_resource(soup, hostname)
            feats['favicon_used']            = extractor.favicon_feature(soup, url, hostname)
            feats['n_hidden_disabled_tags']  = extractor.disabled_status(soup, hostname)
            feats.update(extra_content_features(soup))
            feats['url']   = url
            feats['label'] = label

            if first:
                cols = list(feats.keys())
                out.write(','.join(cols) + '\n')
                first = False

            out.write(','.join(str(feats[c]) for c in cols) + '\n')

    print(f"Wrote {output_csv}")


def main():
    # legit_map = build_mapping(
    #     csv_path     = 'python_training/data/benign_urls.csv',
    #     status_filter=('status', 1),
    #     id_col       = None  # use DataFrame index
    # )
    phish_map = build_mapping(
        csv_path     = 'python_training/data/phishing_urls.csv',
        status_filter=None,
        id_col       = 'phish_id'  # use this column as filename key
    )

    # print(f"Legit entries: {len(legit_map)}")
    print(f"Phish entries: {len(phish_map)}")

    # process_set(legit_map, 'content/html/legitimate', 'features/legit_features.csv', 0)
    process_set(phish_map,   'content/html/phishing',  'features/phish_features.csv', 1)


if __name__ == '__main__':
    main()
