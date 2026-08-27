from tests.addition_fakes import Images
def test_valid_image_is_recognized(tmp_path):
    service=Images(tmp_path);path=service.generate({"job_id":"x"});assert service.valid(str(path)) and service.calls==1
