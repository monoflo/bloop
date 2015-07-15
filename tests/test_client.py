import bloop.client
import botocore
import copy
import pytest
import uuid


def test_batch_get_one_item(User, client):
    ''' A single call for a single item '''
    user1 = User(id=uuid.uuid4())

    request = {'User': {'Keys': [{'id': {'S': str(user1.id)}}],
                        'ConsistentRead': False}}
    # When batching input with less keys than the batch size, the request
    # will look identical
    expected_request = request
    response = {"Responses": {"User": [{'id': {'S': str(user1.id)},
                                        'age': {'N': '4'}}]}}
    # Expected response is a single list of users
    expected_response = {'User': [{'id': {'S': str(user1.id)},
                                   'age': {'N': '4'}}]}

    def handle(RequestItems):
        assert RequestItems == expected_request
        return response
    client.client.batch_get_item = handle

    response = client.batch_get_items(request)
    assert response == expected_response


def test_batch_get_one_batch(User, client):
    ''' A single call when the number of requested items is <= batch size '''
    # Simulate a full batch
    client.batch_size = 2

    user1 = User(id=uuid.uuid4())
    user2 = User(id=uuid.uuid4())

    request = {'User': {'Keys': [{'id': {'S': str(user1.id)}},
                                 {'id': {'S': str(user2.id)}}],
                        'ConsistentRead': False}}
    # When batching input with less keys than the batch size, the request
    # will look identical
    expected_request = request
    response = {"Responses": {"User": [{'id': {'S': str(user1.id)},
                                        'age': {'N': '4'}},
                                       {'id': {'S': str(user2.id)},
                                        'age': {'N': '5'}}]}}
    # Expected response is a single list of users
    expected_response = {'User': [{'id': {'S': str(user1.id)},
                                   'age': {'N': '4'}},
                                  {'id': {'S': str(user2.id)},
                                   'age': {'N': '5'}}]}

    def handle(RequestItems):
        assert RequestItems == expected_request
        return response
    client.client.batch_get_item = handle

    response = client.batch_get_items(request)
    assert response == expected_response


def test_batch_get_paginated(User, client):
    ''' Paginate requests to fit within the max batch size '''
    # Minimum batch size so we can force pagination with 2 users
    client.batch_size = 1

    user1 = User(id=uuid.uuid4())
    user2 = User(id=uuid.uuid4())

    request = {'User': {'Keys': [{'id': {'S': str(user1.id)}},
                                 {'id': {'S': str(user2.id)}}],
                        'ConsistentRead': False}}

    expected_requests = [
        {'User': {'Keys': [{'id': {'S': str(user1.id)}}],
                  'ConsistentRead': False}},
        {'User': {'Keys': [{'id': {'S': str(user2.id)}}],
                  'ConsistentRead': False}}
    ]
    responses = [
        {"Responses": {"User": [{'id': {'S': str(user1.id)},
                                 'age': {'N': '4'}}]}},
        {"Responses": {"User": [{'id': {'S': str(user2.id)},
                                 'age': {'N': '5'}}]}}
    ]
    expected_response = {'User': [{'id': {'S': str(user1.id)},
                                   'age': {'N': '4'}},
                                  {'id': {'S': str(user2.id)},
                                   'age': {'N': '5'}}]}
    calls = 0

    def handle(RequestItems):
        nonlocal calls
        expected = expected_requests[calls]
        response = responses[calls]
        calls += 1
        assert RequestItems == expected
        return response
    client.client.batch_get_item = handle

    response = client.batch_get_items(request)

    assert calls == 2
    assert response == expected_response


def test_batch_get_unprocessed(User, client):
    ''' Re-request unprocessed keys '''
    user1 = User(id=uuid.uuid4())

    request = {'User': {'Keys': [{'id': {'S': str(user1.id)}}],
                        'ConsistentRead': False}}
    expected_requests = [
        {'User': {'Keys': [{'id': {'S': str(user1.id)}}],
                  'ConsistentRead': False}},
        {'User': {'Keys': [{'id': {'S': str(user1.id)}}],
                  'ConsistentRead': False}}
    ]
    responses = [
        {"UnprocessedKeys": {'User': {'Keys': [{'id': {'S': str(user1.id)}}],
                             'ConsistentRead': False}}},
        {"Responses": {"User": [{'id': {'S': str(user1.id)},
                                 'age': {'N': '4'}}]}}
    ]
    expected_response = {'User': [{'id': {'S': str(user1.id)},
                                   'age': {'N': '4'}}]}
    calls = 0

    def handle(RequestItems):
        nonlocal calls
        expected = expected_requests[calls]
        response = responses[calls]
        calls += 1
        assert RequestItems == expected
        return response
    client.client.batch_get_item = handle

    response = client.batch_get_items(request)

    assert calls == 2
    assert response == expected_response


def test_batch_write_one_item(User, client):
    ''' A single call for a single item '''
    user1 = User(id=uuid.uuid4())

    request = {'User': [
        {'PutRequest': {'Item': {'id': {'S': str(user1.id)}}}}]
    }
    # When batching input with less keys than the batch size, the request
    # will look identical
    expected_request = request

    calls = 0

    def handle(RequestItems):
        nonlocal calls
        calls += 1
        assert RequestItems == expected_request
        return {}
    client.client.batch_write_item = handle
    client.batch_write_items(request)
    assert calls == 1


def test_batch_write_one_batch(User, client):
    ''' A single call when the number of requested items is <= batch size '''
    # Simulate a full batch
    client.batch_size = 2

    user1 = User(id=uuid.uuid4())
    user2 = User(id=uuid.uuid4())

    request = {'User': [
        {'PutRequest': {'Item': {'id': {'S': str(user1.id)}}}},
        {'PutRequest': {'Item': {'id': {'S': str(user2.id)}}}}]
    }
    # When batching input with less keys than the batch size, the request
    # will look identical
    expected_request = request

    calls = 0

    def handle(RequestItems):
        nonlocal calls
        calls += 1
        assert RequestItems == expected_request
        return {}
    client.client.batch_write_item = handle

    client.batch_write_items(request)
    assert calls == 1


def test_batch_write_paginated(User, client):
    ''' Paginate requests to fit within the max batch size '''
    # Minimum batch size so we can force pagination with 2 users
    client.batch_size = 1

    user1 = User(id=uuid.uuid4())
    user2 = User(id=uuid.uuid4())

    request = {'User': [
        {'PutRequest': {'Item': {'id': {'S': str(user1.id)}}}},
        {'PutRequest': {'Item': {'id': {'S': str(user2.id)}}}}]
    }
    expected_requests = [
        {'User': [
            {'PutRequest': {'Item': {'id': {'S': str(user1.id)}}}}]},
        {'User': [
            {'PutRequest': {'Item': {'id': {'S': str(user2.id)}}}}]}
    ]
    calls = 0

    def handle(RequestItems):
        nonlocal calls
        expected = expected_requests[calls]
        calls += 1
        assert RequestItems == expected
        return {}
    client.client.batch_write_item = handle

    client.batch_write_items(request)
    assert calls == 2


def test_batch_write_unprocessed(User, client):
    ''' Re-request unprocessed items '''
    user1 = User(id=uuid.uuid4())

    request = {'User': [
        {'PutRequest': {'Item': {'id': {'S': str(user1.id)}}}}]
    }
    expected_requests = [
        {'User': [
            {'PutRequest': {'Item': {'id': {'S': str(user1.id)}}}}]},
        {'User': [
            {'PutRequest': {'Item': {'id': {'S': str(user1.id)}}}}]}
    ]
    responses = [
        {"UnprocessedItems": {'User': [
            {'PutRequest': {'Item': {'id': {'S': str(user1.id)}}}}]}},
        {}
    ]
    calls = 0

    def handle(RequestItems):
        nonlocal calls
        expected = expected_requests[calls]
        response = responses[calls]
        calls += 1
        assert RequestItems == expected
        return response
    client.client.batch_write_item = handle

    client.batch_write_items(request)
    assert calls == 2


def test_call_with_retries(session, client_error):
    max_tries = 4
    tries = 0

    def backoff(operation, attempts):
        nonlocal tries
        tries += 1
        if attempts == max_tries:
            raise RuntimeError("Failed {} after {} attempts".format(
                operation, attempts))
        # Don't sleep at all
        return 0
    client = bloop.client.Client(session=session, backoff_func=backoff)

    def always_raise_retryable(context):
        context['calls'] += 1
        raise client_error(bloop.client.RETRYABLE_ERRORS[0])

    def raise_twice_retryable(context):
        context['calls'] += 1
        if context['calls'] <= 2:
            raise client_error(bloop.client.RETRYABLE_ERRORS[0])

    def raise_unretryable(context):
        context['calls'] += 1
        raise client_error('FooError')

    def raise_non_botocore(context):
        context['calls'] += 1
        raise ValueError('not botocore error')

    # Try the call 4 times, then raise RuntimeError
    tries, context = 0, {'calls': 0}
    with pytest.raises(RuntimeError):
        client.call_with_retries(always_raise_retryable, context)
    assert tries == 4
    assert context['calls'] == 4

    # Fails on first call, first retry, succeeds third call
    tries, context = 0, {'calls': 0}
    client.call_with_retries(raise_twice_retryable, context)
    assert tries == 2
    assert context['calls'] == 3

    # Fails on first call, no retries
    tries, context = 0, {'calls': 0}
    with pytest.raises(botocore.exceptions.ClientError) as excinfo:
        client.call_with_retries(raise_unretryable, context)
    assert tries == 0
    assert context['calls'] == 1
    assert excinfo.value.response['Error']['Code'] == 'FooError'

    # Fails on first call, no retries
    tries, context = 0, {'calls': 0}
    with pytest.raises(ValueError):
        client.call_with_retries(raise_non_botocore, context)
    assert tries == 0
    assert context['calls'] == 1


def test_default_backoff():
    operation = 'foobar'
    attempts = range(bloop.client.DEFAULT_MAX_ATTEMPTS)
    durations = [(50.0 * (2 ** x)) / 1000.0 for x in attempts]

    for (attempts, expected) in zip(attempts, durations):
        actual = bloop.client.default_backoff_func(operation, attempts)
        assert actual == expected

    with pytest.raises(RuntimeError):
        bloop.client.default_backoff_func(
            operation, bloop.client.DEFAULT_MAX_ATTEMPTS)


def test_create_table(ComplexModel, client, ordered):
    expected = {
        'LocalSecondaryIndexes': [
            {'Projection': {'NonKeyAttributes': ['date', 'name',
                                                 'email', 'joined'],
                            'ProjectionType': 'INCLUDE'},
             'IndexName': 'by_joined',
             'KeySchema': [
                {'KeyType': 'HASH', 'AttributeName': 'name'},
                {'KeyType': 'RANGE', 'AttributeName': 'joined'}]}],
        'ProvisionedThroughput': {'ReadCapacityUnits': 3,
                                  'WriteCapacityUnits': 2},
        'GlobalSecondaryIndexes': [
            {'Projection': {'ProjectionType': 'ALL'},
             'IndexName': 'by_email',
             'ProvisionedThroughput': {'ReadCapacityUnits': 4,
                                       'WriteCapacityUnits': 5},
             'KeySchema': [{'KeyType': 'HASH', 'AttributeName': 'email'}]}],
        'TableName': 'CustomTableName',
        'KeySchema': [
            {'KeyType': 'HASH', 'AttributeName': 'name'},
            {'KeyType': 'RANGE', 'AttributeName': 'date'}],
        'AttributeDefinitions': [
            {'AttributeType': 'S', 'AttributeName': 'date'},
            {'AttributeType': 'S', 'AttributeName': 'name'},
            {'AttributeType': 'S', 'AttributeName': 'joined'},
            {'AttributeType': 'S', 'AttributeName': 'email'}]}
    called = False

    def create_table(**table):
        nonlocal called
        called = True
        assert ordered(table) == ordered(expected)
    client.client.create_table = create_table
    client.create_table(ComplexModel)
    assert called


def test_create_raises_unknown(User, client, client_error):
    called = False

    def create_table(**table):
        nonlocal called
        called = True
        raise client_error('FooError')
    client.client.create_table = create_table

    with pytest.raises(botocore.exceptions.ClientError) as excinfo:
        client.create_table(User)
    assert excinfo.value.response['Error']['Code'] == 'FooError'
    assert called


def test_create_already_exists(User, client, client_error):
    called = False

    def create_table(**table):
        nonlocal called
        called = True
        raise client_error('ResourceInUseException')
    client.client.create_table = create_table

    client.create_table(User)
    assert called


def test_delete_item(User, client):
    user_id = uuid.uuid4()
    request = {'Key': {'id': {'S': str(user_id)}},
               'TableName': 'User',
               'ExpressionAttributeNames': {'#n0': 'id'},
               'ConditionExpression': '(attribute_not_exists(#n0))'}
    called = False

    def delete_item(**item):
        nonlocal called
        called = True
        assert item == request
    client.client.delete_item = delete_item
    client.delete_item(request)
    assert called


def test_delete_item_unknown_error(User, client, client_error):
    called = False
    user_id = uuid.uuid4()
    request = {'Key': {'id': {'S': str(user_id)}},
               'TableName': 'User',
               'ExpressionAttributeNames': {'#n0': 'id'},
               'ConditionExpression': '(attribute_not_exists(#n0))'}

    def delete_item(**item):
        nonlocal called
        called = True
        raise client_error('FooError')
    client.client.delete_item = delete_item

    with pytest.raises(botocore.exceptions.ClientError) as excinfo:
        client.delete_item(request)
    assert excinfo.value.response['Error']['Code'] == 'FooError'
    assert called


def test_delete_item_condition_failed(User, client, client_error):
    called = False
    user_id = uuid.uuid4()
    request = {'Key': {'id': {'S': str(user_id)}},
               'TableName': 'User',
               'ExpressionAttributeNames': {'#n0': 'id'},
               'ConditionExpression': '(attribute_not_exists(#n0))'}

    def delete_item(**item):
        nonlocal called
        called = True
        raise client_error('ConditionalCheckFailedException')
    client.client.delete_item = delete_item

    with pytest.raises(bloop.client.ConstraintViolation) as excinfo:
        client.delete_item(request)
    assert excinfo.value.obj == request
    assert called


def test_put_item(User, client):
    user_id = uuid.uuid4()
    request = {'Key': {'id': {'S': str(user_id)}},
               'TableName': 'User',
               'ExpressionAttributeNames': {'#n0': 'id'},
               'ConditionExpression': '(attribute_not_exists(#n0))'}
    called = False

    def put_item(**item):
        nonlocal called
        called = True
        assert item == request
    client.client.put_item = put_item
    client.put_item(request)
    assert called


def test_put_item_unknown_error(User, client, client_error):
    called = False
    user_id = uuid.uuid4()
    request = {'Key': {'id': {'S': str(user_id)}},
               'TableName': 'User',
               'ExpressionAttributeNames': {'#n0': 'id'},
               'ConditionExpression': '(attribute_not_exists(#n0))'}

    def put_item(**item):
        nonlocal called
        called = True
        assert item == request
        raise client_error('FooError')
    client.client.put_item = put_item

    with pytest.raises(botocore.exceptions.ClientError) as excinfo:
        client.put_item(request)
    assert excinfo.value.response['Error']['Code'] == 'FooError'
    assert called


def test_put_item_condition_failed(User, client, client_error):
    called = False
    user_id = uuid.uuid4()
    request = {'Key': {'id': {'S': str(user_id)}},
               'TableName': 'User',
               'ExpressionAttributeNames': {'#n0': 'id'},
               'ConditionExpression': '(attribute_not_exists(#n0))'}

    def put_item(**item):
        nonlocal called
        called = True
        assert item == request
        raise client_error('ConditionalCheckFailedException')
    client.client.put_item = put_item

    with pytest.raises(bloop.client.ConstraintViolation) as excinfo:
        client.put_item(request)
    assert excinfo.value.obj == request
    assert called


def test_describe_table(ComplexModel, client):
    full = {
        'LocalSecondaryIndexes': [
            {'ItemCount': 7,
             'IndexSizeBytes': 8,
             'Projection': {'NonKeyAttributes': ['date', 'name',
                                                 'email', 'joined'],
                            'ProjectionType': 'INCLUDE'},
             'IndexName': 'by_joined',
             'KeySchema': [
                 {'KeyType': 'HASH', 'AttributeName': 'name'},
                 {'KeyType': 'RANGE', 'AttributeName': 'joined'}]}],
        'ProvisionedThroughput': {'ReadCapacityUnits': 3,
                                  'WriteCapacityUnits': 2,
                                  'NumberOfDecreasesToday': 4},
        'GlobalSecondaryIndexes': [
            {'ItemCount': 7,
             'IndexSizeBytes': 8,
             'Projection': {'ProjectionType': 'ALL'},
             'IndexName': 'by_email',
             'ProvisionedThroughput': {'ReadCapacityUnits': 4,
                                       'WriteCapacityUnits': 5,
                                       'NumberOfDecreasesToday': 6},
             'KeySchema': [{'KeyType': 'HASH', 'AttributeName': 'email'}]}],
        'TableName': 'CustomTableName',
        'KeySchema': [
            {'KeyType': 'HASH', 'AttributeName': 'name'},
            {'KeyType': 'RANGE', 'AttributeName': 'date'}],
        'AttributeDefinitions': [
            {'AttributeType': 'S', 'AttributeName': 'date'},
            {'AttributeType': 'S', 'AttributeName': 'name'},
            {'AttributeType': 'S', 'AttributeName': 'joined'},
            {'AttributeType': 'S', 'AttributeName': 'email'}]}

    expected = copy.deepcopy(full)
    expected['ProvisionedThroughput'].pop('NumberOfDecreasesToday')
    gsi = expected['GlobalSecondaryIndexes'][0]
    gsi.pop('ItemCount')
    gsi.pop('IndexSizeBytes')
    gsi['ProvisionedThroughput'].pop('NumberOfDecreasesToday')
    lsi = expected['LocalSecondaryIndexes'][0]
    lsi.pop('ItemCount')
    lsi.pop('IndexSizeBytes')
    called = False

    def describe_table(TableName):
        nonlocal called
        called = True
        assert TableName == ComplexModel.Meta.table_name
        return {"Table": full}
    client.client.describe_table = describe_table

    actual = client.describe_table(ComplexModel)
    assert actual == expected
    assert called


def test_query_scan(User, client):
    def call(**request):
        return responses[request["index"]]

    client.client.query = call
    client.client.scan = call

    responses = [
        {},
        {"Count": -1},
        {"ScannedCount": -1},
        {"Count": 1, "ScannedCount": 2}
    ]

    expecteds = [
        {"Count": 0, "ScannedCount": 0},
        {"Count": -1, "ScannedCount": -1},
        {"Count": 0, "ScannedCount": -1},
        {"Count": 1, "ScannedCount": 2},
    ]

    for index, expected in enumerate(expecteds):
        actual = client.query(index=index)
        assert actual == expected

        actual = client.scan(index=index)
        assert actual == expected


def test_validate_compares_tables(User, client):
    full = {
        'AttributeDefinitions': [
            {'AttributeType': 'S', 'AttributeName': 'id'},
            {'AttributeType': 'S', 'AttributeName': 'email'}],
        'KeySchema': [{'KeyType': 'HASH', 'AttributeName': 'id'}],
        'ProvisionedThroughput': {'ReadCapacityUnits': 1,
                                  'WriteCapacityUnits': 1,
                                  'NumberOfDecreasesToday': 4},
        'GlobalSecondaryIndexes': [
            {'ItemCount': 7,
             'IndexSizeBytes': 8,
             'IndexName': 'by_email',
             'ProvisionedThroughput': {
                 'NumberOfDecreasesToday': 3,
                 'ReadCapacityUnits': 1,
                 'WriteCapacityUnits': 1},
             'KeySchema': [{'KeyType': 'HASH', 'AttributeName': 'email'}],
             'Projection': {'ProjectionType': 'ALL'}}],
        'TableName': 'User'}

    def describe_table(TableName):
        assert TableName == "User"
        return {"Table": full}
    client.client.describe_table = describe_table
    client.validate_table(User)


def test_validate_checks_status(User, client):
    full = {
        'AttributeDefinitions': [
            {'AttributeType': 'S', 'AttributeName': 'id'},
            {'AttributeType': 'S', 'AttributeName': 'email'}],
        'KeySchema': [{'KeyType': 'HASH', 'AttributeName': 'id'}],
        'ProvisionedThroughput': {'ReadCapacityUnits': 1,
                                  'WriteCapacityUnits': 1,
                                  'NumberOfDecreasesToday': 4},
        'GlobalSecondaryIndexes': [
            {'ItemCount': 7,
             'IndexSizeBytes': 8,
             'IndexName': 'by_email',
             'ProvisionedThroughput': {
                 'NumberOfDecreasesToday': 3,
                 'ReadCapacityUnits': 1,
                 'WriteCapacityUnits': 1},
             'KeySchema': [{'KeyType': 'HASH', 'AttributeName': 'email'}],
             'Projection': {'ProjectionType': 'ALL'}}],
        'TableName': 'User'}

    pending = {'TableStatus': 'CREATING'}
    calls = 0

    def describe_table(TableName):
        nonlocal calls
        calls += 1
        assert TableName == "User"
        if calls > 2:
            return {"Table": full}
        return {"Table": pending}
    client.client.describe_table = describe_table
    client.validate_table(User)

    assert calls == 3


def test_validate_fails(ComplexModel, client):
    def describe_table(TableName):
        assert TableName == "CustomTableName"
        return {"Table": {}}
    client.client.describe_table = describe_table
    with pytest.raises(ValueError):
        client.validate_table(ComplexModel)