import json, tempfile, unittest
from pathlib import Path
import pandas as pd
from pipeline import prepare_retail, validate_bike, validate_energy, baseline
from agents import run_team, normalize_model, api_error_message
import io
from urllib.error import HTTPError

class PipelineTests(unittest.TestCase):
    def test_model_display_name_is_normalized(self):
        self.assertEqual(normalize_model(' GPT-5.5 '),'gpt-5.5')

    def test_model_404_explains_access_and_billing(self):
        body=io.BytesIO(b'{"error":{"message":"The model does not exist"}}')
        error=HTTPError('https://api.openai.com/v1/responses',404,'Not Found',{},body)
        message=api_error_message(error,'gpt-5.5')
        self.assertIn('not found or is not available',message)
        self.assertIn('gpt-5-mini',message)
    def test_retail_partitions_and_missing_customer(self):
        df=pd.DataFrame({"InvoiceNo":["1","C2","3","C4","5"],"InvoiceDate":["2011-01-01"]*5,
            "Quantity":[2,-1,-1,2,1],"UnitPrice":[3,3,3,3,0],"CustomerID":[None]*5})
        result=prepare_retail(df)
        self.assertEqual(result.category.tolist(),["sale","credit","excluded","excluded","excluded"])
        self.assertEqual(result.loc[result.category.isin(["sale","credit"]),"value"].sum(),3)

    def test_energy_units_and_invalid_values(self):
        df=pd.DataFrame({"date":pd.date_range("2016-01-01",periods=144,freq="10min"),
            "Appliances":[100]*144,"lights":[10]*144})
        self.assertEqual(validate_energy(df),0)
        self.assertEqual(df.Appliances.sum()/1000,14.4)
        df.loc[0,"Appliances"]=-1
        with self.assertRaises(ValueError): validate_energy(df)

    def test_missing_bike_hour_is_not_zero(self):
        df=pd.DataFrame({"dteday":["2011-01-01"]*2,"hr":[0,2],"cnt":[3,5],"casual":[1,2],"registered":[2,3],
            "timestamp":pd.to_datetime(["2011-01-01 00:00","2011-01-01 02:00"])})
        daily=pd.DataFrame({"dteday":["2011-01-01"],"cnt":[8]})
        self.assertEqual(validate_bike(df,daily),1)
        self.assertEqual(df.cnt.mean(),4)
        df.loc[0,"cnt"]=9
        with self.assertRaises(ValueError):validate_bike(df,daily)

    def test_baseline_does_not_learn_from_test(self):
        df=pd.DataFrame({"time":pd.date_range("2020-01-01",periods=10,freq="h"),"hour":[0]*10,"y":[1]*8+[101]*2})
        result=baseline(df,"time","y",["hour"])
        self.assertEqual(result["seasonal_mae"],100)

    def test_agent_handoffs_without_network(self):
        def fake(role,payload,model):
            if role=="insights": self.assertEqual(set(payload["reviews"]),{"quality","sql"})
            text=json.dumps({"status":"pass","issues":[],"supported_findings":[]}) if role=="reviewer" else "Evidence review"
            return {"role":role,"text":text}
        with tempfile.TemporaryDirectory() as tmp:
            result=run_team({"metrics":{}}, "mock",fake,Path(tmp))
            self.assertEqual(len(result),5)
            self.assertEqual(len(list(Path(tmp).glob("*/AI_REPORT.md"))), 1)
            self.assertEqual(len(list(Path(tmp).glob("*/COMPLETE.json"))), 1)

    def test_review_failure_blocks_report(self):
        def fake(role,payload,model):
            return {"role":role,"text":json.dumps({"status":"revise","issues":["Unsupported claim"],"supported_findings":[]}) if role=="reviewer" else "draft"}
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeError):run_team({},"mock",fake,Path(tmp))
            self.assertFalse(list(Path(tmp).glob("*/AI_REPORT.md")))

    def test_malformed_review_is_rejected(self):
        def fake(role,payload,model):
            return {"role":role,"text":"[]" if role=="reviewer" else "draft"}
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeError):run_team({},"mock",fake,Path(tmp))
            self.assertFalse(list(Path(tmp).glob("*/AI_REPORT.md")))

    def test_failed_rerun_cannot_reuse_prior_report(self):
        def passing(role,payload,model):
            return {"role":role,"text":json.dumps({"status":"pass","issues":[],"supported_findings":[]}) if role=="reviewer" else "draft"}
        def failing(role,payload,model):
            raise RuntimeError("API unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            run_team({},"mock",passing,Path(tmp))
            with self.assertRaises(RuntimeError):run_team({},"mock",failing,Path(tmp))
            self.assertEqual(len(list(Path(tmp).glob("*/COMPLETE.json"))),1)
            self.assertEqual(len(list(Path(tmp).glob("*/RUNNING.json"))),1)

if __name__=="__main__":unittest.main()
