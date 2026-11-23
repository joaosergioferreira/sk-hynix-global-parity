#!/usr/bin/env python3
"""SK hynix global parity dashboard: Python standard library server.

Quotes from public Yahoo Finance Chart endpoints (unofficial, best-effort and delayed).
Provider outages return incomplete data rather than fictitious realtime prices.
"""
import concurrent.futures
import datetime as dt
import json
import os
import pathlib
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parent
STATIC = ROOT / 'static' / 'index.html'
HOST = os.getenv('HOST', '0.0.0.0')
PORT = int(os.getenv('PORT', '8501'))
TTL = int(os.getenv('QUOTE_CACHE_SECONDS', '75'))
NAV = {'hynix_shares': 146100000, 'square_shares': 131923998,
       'other_net_assets_krw': 4690000000000,
       'other_assets_basis': 'SK Square IR 2026-11-20 (non-Hynix assets net of liabilities)'}
SOURCES = {
 '000660': ['000660.KS'], 'HY9H': ['HY9H.F','HY9H.DE','HYXS.L'],
 'SKHY': ['SKHY'], '402340': ['402340.KS'],
 'EURKRW': ['EURKRW=X'], 'USDKRW': ['KRW=X','USDKRW=X']
}
cache = {}
cache_lock = threading.RLock()
UA = ('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36')

def retrieve_chart(symbol, period='5d', interval='5m', prepost=False):
    query = urllib.parse.urlencode({'range':period,'interval':interval,'events':'false',
                                    'includePrePost': 'true' if prepost else 'false'})
    errors=[]
    for domain in ('query1.finance.yahoo.com', 'query2.finance.yahoo.com'):
        url=f'https://{domain}/v8/finance/chart/{urllib.parse.quote(symbol)}?{query}'
        try:
            req=urllib.request.Request(url, headers={
               'User-Agent':UA, 'Accept':'application/json',
               'Referer':'https://finance.yahoo.com/', 'Accept-Language':'en-US,en;q=0.8'})
            with urllib.request.urlopen(req, timeout=10) as resp:
                obj=json.load(resp)
            res = ((obj.get('chart') or {}).get('result') or [None])[0]
            if not res:
                raise ValueError(str((obj.get('chart') or {}).get('error') or 'Empty chart'))
            return res
        except Exception as e:
            errors.append(f'{type(e).__name__}: {str(e)[:105]}')
    raise RuntimeError('; '.join(errors))

def extract_latest(res, ticker, symbol):
    meta=res.get('meta') or {}
    t=res.get('timestamp') or []
    inds=(res.get('indicators') or {}).get('quote') or []
    q=inds[0] if inds else {}
    closes=q.get('close') or []
    bars=[(tm,price) for tm,price in zip(t,closes) if isinstance(price,(float,int)) and price>0]
    # Regular market close for fair common-share parity; do not mix pre/post automatically
    regular=meta.get('regularMarketPrice')
    price=float(regular) if isinstance(regular,(float,int)) and regular>0 else (float(bars[-1][1]) if bars else None)
    if price is None: raise ValueError('No valid price')
    quote_time=meta.get('regularMarketTime') or (bars[-1][0] if bars else None)
    quote_time_iso=dt.datetime.fromtimestamp(int(quote_time),dt.timezone.utc).isoformat() if quote_time else None
    return {'symbol':ticker,'resolved_symbol':symbol,'price':round(price,5),
            'currency':meta.get('currency'),'market_time':quote_time_iso,
            'exchange_timezone':meta.get('exchangeTimezoneName'),
            'exchange':meta.get('exchangeName'), 'source':'Yahoo Finance (unofficial)',
            'delay_unknown':True, 'market_state':'regular or last official trade',
            'as_of_retrieved':dt.datetime.now(dt.timezone.utc).isoformat()}

def fetch_quote(ticker):
    errs=[]
    for sym in SOURCES[ticker]:
        for interval in ('5m','1d'):
            try:
                # 1d may be used when intraday history is not available on that venue
                res=retrieve_chart(sym,period='5d', interval=interval)
                out=extract_latest(res,ticker,sym)
                if ticker=='HY9H' and out['currency'] != 'EUR':
                    # Never silently mix USD denominated Luxembourg GDR in an EUR leg
                    errs.append(f'{sym} quoted in {out["currency"]}, not EUR')
                    continue
                return out
            except Exception as e:
                errs.append(f'{sym}/{interval}: {str(e)[:115]}')
    return {'symbol':ticker, 'price':None,'error':' | '.join(errs[-3:]),
            'source':'Yahoo Finance (unofficial)'}

def get_snapshot():
    def build():
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            f={k:pool.submit(fetch_quote,k) for k in SOURCES}
            data={k:v.result() for k,v in f.items()}
        return {'time_retrieved':dt.datetime.now(dt.timezone.utc).isoformat(),
                'quotes':data,'nav_parameters':NAV,
                'provider_note':'Yahoo chart is unofficial. Data may be delayed; timestamps refer to original venue trades, not page refresh.',
                'cached_for_seconds':TTL}
    return cached('snapshot',TTL,build)

def fetch_history(ticker,period):
    errs=[]
    for symbol in SOURCES[ticker]:
        try:
            obj=retrieve_chart(symbol, period=period, interval='1d')
            currency=(obj.get('meta') or {}).get('currency')
            if ticker=='HY9H' and currency!='EUR':continue
            times=obj.get('timestamp') or []
            ind=(obj.get('indicators') or {}).get('quote') or []
            q=ind[0] if ind else {}
            close=q.get('close') or []
            points=[]
            for tm,p in zip(times,close):
                if not isinstance(p,(float,int)) or p<=0:continue
                day=dt.datetime.fromtimestamp(tm,dt.timezone.utc).strftime('%Y-%m-%d')
                points.append({'date':day,'price':round(float(p),6)})
            return {'resolved_symbol':symbol,'currency':currency,'points':points}
        except Exception as e:errs.append(f'{symbol}: {str(e)[:100]}')
    return {'points':[],'error':' | '.join(errs[-3:])}

def history(period):
    def build():
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            f={k:pool.submit(fetch_history,k,period) for k in SOURCES}
            series={k:v.result() for k,v in f.items()}
        ix={k:{p['date']:p['price'] for p in v.get('points',[])} for k,v in series.items()}
        dates=sorted(set(ix['000660']) | set(ix['402340']))
        rows=[]
        for date in dates:
            # Same-date end-of-day observations are not synchronized executions.
            krw=ix['000660'].get(date)
            eur=ix['EURKRW'].get(date)
            usd=ix['USDKRW'].get(date)
            h=ix['HY9H'].get(date)
            a=ix['SKHY'].get(date)
            square=ix['402340'].get(date)
            premium_gdr=(100*(h*eur/krw-1)) if h and eur and krw else None
            premium_adr=(100*(a*10*usd/krw-1)) if a and usd and krw else None
            nav=(krw*NAV['hynix_shares']+NAV['other_net_assets_krw'])/NAV['square_shares'] if krw else None
            square_discount=(100*(1-square/nav)) if square and nav else None
            if any(v is not None for v in (premium_gdr,premium_adr,square_discount)):
                rows.append({'date':date,'gdr':premium_gdr,'adr':premium_adr,
                             'square_discount':square_discount})
        return {'period':period,'rows':rows,'time_retrieved':dt.datetime.now(dt.timezone.utc).isoformat(),
                'series_errors':{k:v.get('error') for k,v in series.items() if v.get('error')},
                'methodology':'Same-calendar-day closing comparison, not simultaneous; historical FX per matching date.'}
    return cached('history:'+period,900,build)

def cached(key,seconds,builder):
    now=time.monotonic()
    with cache_lock:
        item=cache.get(key)
        if item and item[0]>now:return item[1]
    result=builder()
    with cache_lock:
        cache[key]=(time.monotonic()+seconds,result)
    return result

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url=urllib.parse.urlparse(self.path)
        try:
            if url.path in ('/','/index.html'):
                data=STATIC.read_bytes()
                self.send_out(200,data,'text/html; charset=utf-8')
            elif url.path=='/api/snapshot':
                self.send_json(get_snapshot())
            elif url.path=='/api/history':
                period=urllib.parse.parse_qs(url.query).get('range',['3mo'])[0]
                if period not in ('1mo','3mo','6mo','1y'):
                    self.send_json({'error':'range must be 1mo, 3mo, 6mo, or 1y'},400);return
                self.send_json(history(period))
            elif url.path=='/api/health':
                self.send_json({'status':'ok','time':dt.datetime.now(dt.timezone.utc).isoformat()})
            else: self.send_json({'error':'Not found'},404)
        except Exception as e:
            self.send_json({'error':f'{type(e).__name__}: {str(e)[:350]}'},503)

    def send_json(self,obj,status=200):
        self.send_out(status,json.dumps(obj,ensure_ascii=False).encode('utf-8'),'application/json; charset=utf-8')

    def send_out(self,status,data,mime):
        self.send_response(status)
        self.send_header('Content-Type',mime)
        self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store, max-age=0')
        self.send_header('X-Content-Type-Options','nosniff')
        self.end_headers();self.wfile.write(data)

    def log_message(self,*args):pass

if __name__=='__main__':
    print(f'SK hynix parity dashboard → http://127.0.0.1:{PORT}',flush=True)
    ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
