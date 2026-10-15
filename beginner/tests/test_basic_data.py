import uuid


def test_create_depots_and_material(client, data):
    depots = client.listing('depot', {'name': data['tag']})
    assert depots['total'] == 2
    assert {row['id'] for row in depots['rows']} == {data['a'], data['b']}
    material = client.listing('material', {'materialParam': data['tag']})
    assert material['total'] == 1
    assert material['rows'][0]['id'] == data['material']


def test_depot_pagination(client, data):
    search = {'name': data['tag']}
    first = client.listing('depot', search, page=1, size=1)
    second = client.listing('depot', search, page=2, size=1)
    assert first['total'] == second['total'] == 2
    assert len(first['rows']) == len(second['rows']) == 1
    assert first['rows'][0]['id'] != second['rows'][0]['id']


def test_no_matching_depot(client):
    result = client.listing('depot', {'name': 'QA_ABSENT_' + uuid.uuid4().hex})
    assert result['total'] == 0
    assert result['rows'] == []
