import json
import os
import numpy as np
import pandas as pd
import re
from tqdm import tqdm
from collections import namedtuple
# from utils.eval_utils import compute_f1

def compute_f1(predicts, labels):
    tp = 0
    pos = 0
    true = 0
    for p, l in zip(predicts, labels):
        true += len(l)
        pos += len(p)
        tp += len(p & l)
    precision = tp / pos if pos != 0 else 0
    recall = tp / true if true != 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) != 0 else 0
    return precision, recall, f1

class Task(object):

    def __init__(self, task_name, task_elements) -> None:
        self.task_name = task_name
        self.task_elements = task_elements
        self.Result = namedtuple(task_name, task_elements)
        self.contexts = []
        self.predicts = []
        self.labels = []

    def _json_to_result(self, jobj):
        e = ["NULL" if jobj[k] is None else jobj[k] for k in self.task_elements]
        return self.Result(*e)

    def parse(self, context, predict, label):
        p_set = set(self._json_to_result(each) for each in predict)
        l_set = set(self._json_to_result(each) for each in label)
        if "Implicity" in self.task_name:
            p_set = set(each for each in p_set if each.target == "NULL")
            l_set = set(each for each in l_set if each.target == "NULL")
            # if "Implicity_Only" in self.task_name:
            #     if all(each.target == "NULL" for each in l_set):
            #         self.contexts.append(context)
            #         self.predicts.append(p_set)
            #         self.labels.append(l_set)
            # else:
            #     if any(each.target == "NULL" for each in l_set):
            #         self.contexts.append(context)
            #         self.predicts.append(p_set)
            #         self.labels.append(l_set)
        # else:
        elif "Mixed" in self.task_name:
            if len(set((each.aspect, each.polarity) for each in l_set)) <= 1: 
                return
                
        self.contexts.append(context)
        self.predicts.append(p_set)
        self.labels.append(l_set)

    def evaluate(self):
        return compute_f1(self.predicts, self.labels)

    def reset(self):
        self.contexts = []
        self.predicts = []
        self.labels = []


class MultiTaskEvaluatior(object):

    def __init__(self, task_config, output_dir) -> None:
        self.task_pools = {}
        self.output_dir = output_dir
        for name, elements in task_config.items():
            self.task_pools[name] = Task(name, elements)

        files = sorted([fn for fn in os.listdir(output_dir) if fn.endswith(".json")], key=lambda x: int(re.match('epoch(\d+)_', x).group(1)))
        self.output_results = [json.load(open(os.path.join(output_dir, fn))) for fn in files]
        self.eval_results = {k: {"p": [], "r": [], "f1": []}
                             for k in task_config}

    def eval_epoch_task(self, epoch, task_name):
        self.parse(epoch)
        self.eval(task_name)

    def parse(self, epoch):
        output_result = self.output_results[epoch]
        for test_case in output_result:
            context = test_case["context"]
            for task in self.task_pools.values():
                task.parse(context, test_case["predict"], test_case["label"])

    def eval(self, task_name):
        task = self.task_pools[task_name]
        p, r, f1 = task.evaluate()
        self.eval_results[task.task_name]["p"].append(p)
        self.eval_results[task.task_name]["r"].append(r)
        self.eval_results[task.task_name]["f1"].append(f1)

    def reset(self):
        for task in self.task_pools.values():
            task.reset()

    def display(self, save=False):
        best_results = []
        for name, results in self.eval_results.items():
            best_epoch = np.argmax(results["f1"])
            best_results.append({
                "epoch": best_epoch+1,
                "p": results["p"][best_epoch],
                "r": results["r"][best_epoch],
                "f1": results["f1"][best_epoch]
            })
        df = pd.DataFrame(data=best_results, index=self.eval_results.keys())
        if save:
            df.to_csv(os.path.join(self.output_dir, "eval_results.csv"))

        print(df)
        print()
        return df

    def full_evaluate(self, save=False):
        for epoch in tqdm(range(len(self.output_results))):
            self.parse(epoch)
            for task_name in self.task_pools:
                self.eval(task_name)
            self.reset()
        return self.display(save=save)


TASK_CONFIG = {
    "A": ["aspect"],
    "T": ["target"],
    "TA": ["target", "aspect"],
    "AS": ["aspect", "polarity"],
    "TS": ["target", "polarity"],
    "TAS": ["target", "aspect", "polarity"],
    "TAS_Implicity_Only": ["target", "aspect", "polarity"],
    "Mixed_sentence": ["target", "aspect", "polarity"],
}


if __name__ == "__main__":
    res15_results = []
    res16_results = []
    laptop_results = []
    output_dir = "output"
    contains = ["res16", "fix"]
    not_contains = []
    re_evaluate = False
    save_res = True
    def get_best_epoch_result_for_each_task(epoch, path):
        evaluator = MultiTaskEvaluatior(TASK_CONFIG, path)
        evaluator.parse(epoch - 1)
        for task in TASK_CONFIG:
            evaluator.eval(task)
            print("{:<25} {}".format(task, evaluator.eval_results[task]))

    for exp in os.listdir(output_dir):
        if contains and not all(map(lambda x:x in exp, contains)):
            continue

        if not_contains and any(map(lambda x:x in exp, not_contains)):
            continue
        print(exp)
        if not re_evaluate and "eval_results.csv" in os.listdir(f"{output_dir}/{exp}"):
            df = pd.read_csv(f"{output_dir}/{exp}/eval_results.csv", index_col="Unnamed: 0")
            get_best_epoch_result_for_each_task(df.loc["TAS", "epoch"], f"{output_dir}/{exp}")
            print(df)
            print()
            if "res15" in exp:
                res15_results.append((exp,df)) 
            elif "res16" in exp:
                res16_results.append((exp,df))
            elif "laptop" in exp:
                laptop_results.append((exp,df))
            continue
        try:
            evaluator = MultiTaskEvaluatior(TASK_CONFIG, f"{output_dir}/{exp}")
            df = evaluator.full_evaluate(save_res)
            get_best_epoch_result_for_each_task(df.loc["TAS", "epoch"], f"{output_dir}/{exp}")
            res15_results.append((exp,df)) if "res15" in exp else res16_results.append((exp,df))
        except Exception as e:
            print(e)
            print()
            continue


    def get_best_score_each_task(results):
        # res = {"AS":[], "TS":[], "TA":[], "A":[], "T":[], "TAS":[]}
        res = {task: [] for task in TASK_CONFIG}
        for exp, df in results:
            for task in res:
                res[task].append((df.loc[task]["f1"], exp))
        for k,v in res.items():
            v.sort(key=lambda x:x[0], reverse=True)
            print(f"{k}: Best f1:{v[0][0]}; Experiment:{v[0][1]}")
        return res
    if len(res15_results):
        print("Res15:")
        res15_scores = get_best_score_each_task(res15_results)
    if len(res16_results):
        print("\nRes16:")
        res16_scores = get_best_score_each_task(res16_results)
    if len(laptop_results):
        print("\nLaptop:")
        res16_scores = get_best_score_each_task(laptop_results)



        
