from django.test import TestCase


class ImmunizationTest(TestCase):
    
    def test_extract_immunization_type_name(self):
        data = {
            'bcg': {'wt24h': '1', 'd0': '2025-10-06', 'd1': None, 'd2': None, 'd3': None},
            'hepb': {'wt24h': None, 'd0': None, 'd1': '2025-10-06', 'd2': None, 'd3': None},
            'pcv': {'wt24h': '1', 'd0': None, 'd1': None, 'd2': '2025-10-06', 'd3': None},
            'opv': {'wt24h': '1', 'd0': None, 'd1': None, 'd2': None, 'd3': '2025-10-06'},
            'amv': {'wt24h': '1', 'd0': None, 'd1': None, 'd2': None, 'd3': None},
            'penta': {'wt24h': '1', 'd0': None, 'd1': None, 'd2': None, 'd3': None}
        }
        
        for key in data.keys():
            
            if key == "penta":
                key = "pentavalent"
            
            # print(f"Immunization Type Name: {key.upper()}")

    def test_immunization_logic(self):

        data = {
        'bcg': {'wt24h': '1', 'd0': '2025-10-06', 'd1': None, 'd2': None, 'd3': None},
        'hepb': {'wt24h': None, 'd0': None, 'd1': '2025-10-06', 'd2': None, 'd3': None},
        'pcv': {'wt24h': '1', 'd0': None, 'd1': None, 'd2': '2025-10-06', 'd3': None},
        'opv': {'wt24h': '1', 'd0': None, 'd1': None, 'd2': '2025-10-06', 'd3': '2025-10-06'},
        'amv': {'wt24h': '1', 'd0': None, 'd1': None, 'd2': None, 'd3': None},
        'penta': {'wt24h': '1', 'd0': None, 'd1': None, 'd2': None, 'd3': None}
    }

        STAGE_MAP = {"d0": 1, "d1": 2, "d2": 3, "d3": 4}
        PRIORITY = ["d3", "d2", "d1", "d0"]

        for vaccine, doses in data.items():
            stage = 0  
            for dose_key in PRIORITY:
                if doses.get(dose_key):
                    stage = STAGE_MAP[dose_key]
                    break
            doses['stage'] = stage

        print(data)
                
        # for key, value in data.items():
        #     stage = 0
        #     for i, k in enumerate(STAGES, 1):
        #         if value.get(k):
        #             stage = i
        #         else:
        #             break
        #     data[key]['stage'] = stage
            
        # print(data)
            
        
        # for key, value in data.items():
        #     print(key, value)
        #     if value['wt24h'] == '1':
        #         stage = 1
        #     elif value['d0']:
        #         stage = 2
        #     elif value['d1']:
        #         stage = 3
        #     elif value['d2']:
        #         stage = 4
        #     elif value['d3']:
        #         stage = 5
        #     else:
        #         stage = None
            
        #     print(f"Immunization: {key}, Stage: {stage}")
