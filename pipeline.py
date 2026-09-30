"""Reproducible three-industry analytics. Run: python pipeline.py --download."""
import argparse, hashlib, io, json, sqlite3, sys, zipfile, urllib.request
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "artifacts"
SOURCES = {
 "retail": ("https://archive.ics.uci.edu/static/public/352/online+retail.zip", "Online Retail.xlsx"),
 "bike": ("https://archive.ics.uci.edu/static/public/275/bike+sharing+dataset.zip", "hour.csv"),
 "energy": ("https://archive.ics.uci.edu/static/public/374/appliances+energy+prediction.zip", "energydata_complete.csv")
}
LIMITS = {
 "retail": "Recorded transaction value in GBP, not profit or accounting revenue. Exact duplicates retained because repeated lines may be legitimate. Positive-price sales and cancellation credits only; other adjustments excluded. Missing customers retained for sales, excluded from repeat-customer metrics. December 2011 is partial.",
 "bike": "Observed rentals in one system, not unique riders or unmet demand. Missing hours remain missing. Profiles average observed hours only. No causal or station-level conclusions.",
 "energy": "One dwelling over part of a year. Appliances is Wh per 10-minute interval; sum/1000 yields kWh. Lighting is separate. Partial days excluded from complete-day averages. No demonstrated savings or annual generalization."
}

def save_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")

def download():
    RAW.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for name, (url, filename) in SOURCES.items():
        archive = RAW / (name + ".zip")
        if not archive.exists():
            print("Downloading", name, flush=True)
            with urllib.request.urlopen(url, timeout=120) as r:
                content = r.read()
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                if z.testzip():
                    raise ValueError("Corrupt archive: " + name)
            archive.write_bytes(content)
        with zipfile.ZipFile(archive) as z:
            wanted = [filename] + (["day.csv"] if name == "bike" else [])
            for target in wanted:
                matches = [n for n in z.namelist() if Path(n).name == target]
                if len(matches) != 1:
                    raise ValueError("Expected archive member: " + target)
                (RAW / target).write_bytes(z.read(matches[0]))
        manifest[name] = {"url": url, "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                          "file_sha256": hashlib.sha256((RAW / filename).read_bytes()).hexdigest(),
                          "bytes": (RAW / filename).stat().st_size}
    save_json(RAW / "manifest.json", manifest)

def prepare_retail(frame):
    df = frame.copy()
    df["InvoiceNo"] = df.InvoiceNo.astype("string")
    df["InvoiceDate"] = pd.to_datetime(df.InvoiceDate, errors="raise")
    for field in ("Quantity", "UnitPrice"):
        df[field] = pd.to_numeric(df[field], errors="raise")
        if not np.isfinite(df[field]).all():
            raise ValueError("Nonfinite retail numeric values")
    cancel = df.InvoiceNo.str.upper().str.startswith("C").fillna(False)
    required = df.InvoiceNo.notna() & df.InvoiceDate.notna()
    sale = required & ~cancel & (df.Quantity > 0) & (df.UnitPrice > 0)
    credit = required & cancel & (df.Quantity < 0) & (df.UnitPrice > 0)
    df["category"] = np.select([sale, credit], ["sale", "credit"], default="excluded")
    df["value"] = df.Quantity * df.UnitPrice
    return df

def profile(df):
    return {"rows": len(df), "exact_duplicate_rows": int(df.duplicated().sum()),
            "missing": {k: int(v) for k,v in df.isna().sum().items() if v}}

def validate_bike(df, daily):
    if df.timestamp.isna().any() or df.timestamp.duplicated().any():
        raise ValueError("Invalid or duplicate bike timestamp")
    if not df.hr.between(0,23).all():
        raise ValueError("Invalid bike hour")
    for col in ("cnt", "casual", "registered"):
        if not ((df[col] >= 0) & (df[col] % 1 == 0)).all():
            raise ValueError("Invalid bike counts")
    if not (df.cnt == df.casual + df.registered).all():
        raise ValueError("Bike components do not reconcile")
    totals = df.groupby("dteday").cnt.sum()
    expected = daily.set_index("dteday").cnt
    pd.testing.assert_series_equal(totals.sort_index(), expected.sort_index(), check_names=False)
    return int(len(pd.date_range(df.timestamp.min(), df.timestamp.max(), freq="h")) - len(df))

def validate_energy(df):
    if df.date.isna().any() or df.date.duplicated().any():
        raise ValueError("Invalid or duplicate energy timestamp")
    if not np.isfinite(df[["Appliances","lights"]].to_numpy()).all():
        raise ValueError("Nonfinite energy")
    if not (df[["Appliances","lights"]] >= 0).all().all():
        raise ValueError("Negative energy")
    gaps = df.date.sort_values().diff().dropna()
    return int((gaps != pd.Timedelta(minutes=10)).sum())

def baseline(df, time_col, target, groups):
    df = df.sort_values(time_col)
    split = int(len(df)*0.8)
    train, test = df.iloc[:split], df.iloc[split:]
    if not train[time_col].max() < test[time_col].min():
        raise ValueError("Temporal overlap")
    means = train.groupby(groups)[target].mean()
    prediction = test[groups].merge(means.rename("prediction"), left_on=groups,
                                    right_index=True, how="left").prediction.fillna(train[target].mean())
    actual = test[target].to_numpy()
    return {"train_rows": len(train), "test_rows": len(test),
            "test_start": str(test[time_col].min()),
            "seasonal_mae": float(np.abs(actual-prediction.to_numpy()).mean()),
            "constant_mean_mae": float(np.abs(actual-train[target].mean()).mean()),
            "note": "First 80% trains group means; final 20% tests. Descriptive baseline comparison, not a tuned model."}

def chart(tables, metrics):
    image = Image.new("RGB", (1800, 1300), "#0d1729")
    draw = ImageDraw.Draw(image)
    def font(size):
        for path in ("C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
            if Path(path).exists(): return ImageFont.truetype(path, size)
        return ImageFont.load_default()
    draw.text((60,40), "THREE INDUSTRIES. ONE ANALYTICS WORKFLOW.", font=font(38), fill="#eef4ff")
    draw.text((60,99), "Historical public data | Python + SQL | Reproducible evidence", font=font(23), fill="#9eb1cf")
    panels = [
        ("Retail / monthly gross transaction value", tables["retail_monthly"], "month", "gross_gbp", "GBP", "#52d8c4"),
        ("Transportation / average rentals by hour", tables["bike_hourly"].groupby("hr",as_index=False).apply(
            lambda g: pd.Series({"mean_rentals": np.average(g.mean_rentals,weights=g.observed_hours)}),
            include_groups=False), "hr", "mean_rentals", "rentals / observed hour", "#77aaff"),
        ("Energy / average appliance consumption", tables["energy_hourly"], "hour", "mean_wh", "Wh / 10-minute interval", "#dba2ff")]
    for i,(title,df,label,value,unit,color) in enumerate(panels):
        x,y,w,h = 60, 165+i*350,1680,320
        draw.rounded_rectangle((x,y,x+w,y+h), radius=16, fill="#17243b")
        draw.text((x+25,y+18),title,font=font(27),fill="white")
        draw.text((x+25,y+56),unit,font=font(18),fill="#a9bbd7")
        vals=df[value].tolist(); labels=df[label].astype(str).tolist(); maximum=max(vals) or 1
        left=x+105; bottom=y+265; width=w-145; height=155
        draw.text((x+15,y+98), f"{maximum:,.0f}",font=font(17),fill="#a9bbd7")
        draw.text((x+65,bottom-10),"0",font=font(17),fill="#a9bbd7")
        step=width/len(vals)
        for j,(v,l) in enumerate(zip(vals,labels)):
            bx=left+j*step
            draw.rectangle((bx,bottom-v/maximum*height,bx+step*0.72,bottom),fill=color)
            draw.text((bx,bottom+10), l[2:] if i==0 else l,font=font(15),fill="#cad6e9")
    draw.text((60,1230), "Retail final month is partial. Bike hours are observed only. Energy covers one dwelling.",font=font(21),fill="#b6c6df")
    image.save(OUT / "dashboard.png")

def run():
    OUT.mkdir(exist_ok=True)
    retail_raw = pd.read_excel(RAW / "Online Retail.xlsx", dtype={"InvoiceNo":"string","StockCode":"string","CustomerID":"string"})
    retail = prepare_retail(retail_raw)
    bike = pd.read_csv(RAW / "hour.csv")
    bike["timestamp"] = pd.to_datetime(bike.dteday) + pd.to_timedelta(bike.hr,unit="h")
    energy = pd.read_csv(RAW / "energydata_complete.csv")
    energy["date"] = pd.to_datetime(energy.date, errors="raise")
    quality = {"retail": profile(retail_raw), "bike": profile(bike), "energy": profile(energy)}
    quality["retail"]["partitions"] = {k:int(v) for k,v in retail.category.value_counts().items()}
    quality["retail"]["excluded_signed_value_gbp"] = float(retail.loc[retail.category=="excluded","value"].sum())
    quality["bike"]["missing_hours"] = validate_bike(bike,pd.read_csv(RAW/"day.csv"))
    quality["energy"]["non_10_minute_gaps"] = validate_energy(energy)
    tables={}
    with sqlite3.connect(OUT / "analytics.sqlite") as con:
        for name,df in (("retail",retail),("bike",bike),("energy",energy)):
            df.to_sql(name,con,if_exists="replace",index=False)
        for path in sorted((ROOT/"sql").glob("*.sql")):
            tables[path.stem] = pd.read_sql_query(path.read_text(),con)
            tables[path.stem].to_csv(OUT/(path.stem+".csv"),index=False)
    sales=retail[retail.category=="sale"]; credits=retail[retail.category=="credit"]
    customer_orders=sales.dropna(subset=["CustomerID"]).groupby("CustomerID").InvoiceNo.nunique()
    day=tables["energy_daily"]; complete=day[day.observations==144]
    metrics = {
      "retail": {"source_rows":len(retail),"gross_gbp":float(sales.value.sum()),
        "credits_gbp":float(-credits.value.sum()),"net_gbp":float(sales.value.sum()+credits.value.sum()),
        "orders":int(sales.InvoiceNo.nunique()),"gross_order_value_gbp":float(sales.value.sum()/sales.InvoiceNo.nunique()),
        "identified_customers":len(customer_orders),"repeat_customer_share":float((customer_orders>1).mean())},
      "bike": {"source_rows":len(bike),"rentals":int(bike.cnt.sum()),"mean_rentals_observed_hour":float(bike.cnt.mean())},
      "energy": {"source_rows":len(energy),"appliance_kwh":float(energy.Appliances.sum()/1000),
        "complete_days":len(complete),"partial_days":int((day.observations!=144).sum()),
        "mean_complete_day_kwh":float(complete.appliance_kwh.mean())}}
    checks={
      "retail_row_partition":sum(quality["retail"]["partitions"].values())==len(retail),
      "retail_sql_total":bool(np.isclose(tables["retail_monthly"].net_gbp.sum(),metrics["retail"]["net_gbp"])),
      "retail_order_reconciliation":bool(np.isclose(sales.groupby("InvoiceNo").value.sum().sum(),sales.value.sum())),
      "bike_sql_total":int(tables["bike_monthly"].rentals.sum())==int(bike.cnt.sum()),
      "bike_components_and_daily_reconciliation":True,
      "energy_sql_total":bool(np.isclose(day.appliance_kwh.sum(),energy.Appliances.sum()/1000)),
      "energy_cadence":quality["energy"]["non_10_minute_gaps"]==0}
    if not all(checks.values()): raise ValueError("Reconciliation failed: "+str(checks))
    energy["hour"]=energy.date.dt.hour
    energy["minute"]=energy.date.dt.minute
    evaluations = {"bike":baseline(bike,"timestamp","cnt",["weekday","hr"]),
                   "energy":baseline(energy,"date","Appliances",["hour","minute"])}
    evidence = {"generated_utc":datetime.now(timezone.utc).isoformat(),"mode":"deterministic",
        "metrics":metrics,"quality":quality,"checks":checks,"baseline_evaluation":evaluations,
        "limitations":LIMITS,"tables":{k:json.loads(v.to_json(orient="records")) for k,v in tables.items()},
        "sql":{p.name:p.read_text() for p in (ROOT/"sql").glob("*.sql")},
        "source_manifest":json.loads((RAW/"manifest.json").read_text())}
    save_json(OUT/"evidence.json",evidence)
    save_json(OUT/"validation.json",checks)
    chart(tables,metrics)
    lines=["# Three-industry analysis report","",
      "Executed mode: deterministic Python/SQL. Live LLM reviews are a separate opt-in run.","",
      "![Dashboard](dashboard.png)",""]
    for name in metrics:
        lines += ["## "+name.title(),""]
        for key,value in metrics[name].items():
            label=key.replace("_", " ").capitalize().replace("gbp", "(GBP)").replace("kwh", "(kWh)")
            formatted=f"{value:.1%}" if key.endswith("share") else (f"{value:,.2f}" if isinstance(value,float) else f"{value:,}")
            lines += [f"- **{label}**: {formatted}"]
        lines += ["",LIMITS[name],""]
    peak_b=tables["bike_hourly"].sort_values("mean_rentals",ascending=False).iloc[0]
    peak_e=tables["energy_hourly"].sort_values("mean_wh",ascending=False).iloc[0]
    top=tables["retail_countries"].iloc[0]
    lines += ["## Findings and proposed actions","",
      f"- Retail: {top.Country} has the largest gross transaction value ({top.gross_gbp:,.2f} GBP). Investigate market concentration before recommending expansion.",
      f"- Bike: the highest hour/working-day group averages {peak_b.mean_rentals:,.1f} rentals at hour {int(peak_b.hr):02d}, workingday={int(peak_b.workingday)}. Investigate staffing needs; station-level allocation needs station data.",
      f"- Energy: hour {int(peak_e.hour):02d} has the largest mean appliance reading ({peak_e.mean_wh:.1f} Wh per interval). Investigate appliance schedules; savings require an intervention study.","",
      "## Quality and baseline evaluation","",
      "All reconciliation gates passed. Exact duplicates are reported and retained. Detailed missingness, excluded rows, source hashes, and chronological baseline MAE are in evidence.json.",
      "The seasonal baseline uses training-only group means and is compared with a training-only constant mean. No tuned predictive model is claimed.","",
      "| Dataset | Time-group baseline MAE | Constant-mean baseline MAE | Units |",
      "|---|---:|---:|---|",
      f"| Bike | {evaluations['bike']['seasonal_mae']:.2f} | {evaluations['bike']['constant_mean_mae']:.2f} | Rentals per observed hour |",
      f"| Energy | {evaluations['energy']['seasonal_mae']:.2f} | {evaluations['energy']['constant_mean_mae']:.2f} | Wh per 10-minute interval |","",
      f"Data-quality findings: {quality['retail']['exact_duplicate_rows']:,} exact retail duplicates retained; {quality['retail']['partitions'].get('excluded',0):,} retail rows excluded from scoped value metrics; {quality['bike']['missing_hours']} absent bike hours; {metrics['energy']['partial_days']} partial energy days.","",
      "## Sources","","See ../SOURCES.md for authors, original datasets, licenses and scope."]
    (OUT/"REPORT.md").write_text("\n".join(lines),encoding="utf-8")
    print(json.dumps({"metrics":metrics,"checks":checks,"evaluations":evaluations},indent=2))
    return evidence

if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--download",action="store_true")
    parser.add_argument("--agents",action="store_true",help="Opt in to paid OpenAI requests using aggregate evidence")
    parser.add_argument("--model",default=None)
    args=parser.parse_args()
    try:
        if args.download: download()
        evidence=run()
        if args.agents:
            import os
            from agents import run_team
            run_team(evidence,args.model or os.environ.get("OPENAI_MODEL"))
    except Exception as error:
        print(f"Run failed: {error}",file=sys.stderr)
        sys.exit(1)
