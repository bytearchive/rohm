
import pytest
from mock import call

from rohm.models import Model
from rohm import fields
from rohm.exceptions import DoesNotExist
# from redis.client import StrictPipeline


@pytest.fixture
def Foo():
    class Foo(Model):
        name = fields.CharField()
        num = fields.IntegerField()
    return Foo


def test_simple_model(pipe, Foo):

    id = 1
    name = 'foo'
    num = 123
    foo = Foo(id=id, name=name, num=num)

    # Basic attribute access

    def check_attrs(foo):

        assert foo.id == id
        assert foo.name == name
        assert foo.num == num

    check_attrs(foo)
    foo.save()

    foo = Foo.get(id=1)
    check_attrs(foo)

    # Change a field
    foo.num = 456
    foo.save()

    foo = Foo.get(1)
    assert foo.num == 456

    # Getting non-existent model
    with pytest.raises(DoesNotExist):
        Foo.get(id=2)

    # Test saving without id should fail
    foo = Foo(name='1', num=2)
    with pytest.raises(Exception):
        foo.save()


class TestNoneField(object):

    def test_none_field_basics(self, conn):

        """
        Test behavior of allow_none fields
        - reading a field that is None
        - loading an object with a None field, we should distinguish between knowing that a field is
          None, vs not having loaded the field at all
        - try saving a field from None -> something, and vice versa
        """

        class Foo(Model):
            name = fields.CharField()
        return Foo

        foo = Foo(id=1)
        assert foo.name is None
        foo.save()

        redis_key = 'foo:1'

        # should be no calls get (bug with name __get__ calling from Redis)
        assert conn.hmget.call_count == 0

        conn.reset_mock()

        # understand that we already "loaded" that this field is None
        foo = Foo.get(id=1)
        assert conn.mock_calls == [call.hgetall(redis_key)]
        assert foo._loaded_field_names == {'id', 'name'}

        assert foo.name is None   # this should not trigger Redis call

        foo.name = 'asdf'
        assert foo._get_modified_fields() == {'name': 'asdf'}
        foo.save()
        assert conn.mock_calls[-1] == call.hmset(redis_key, {'name': 'asdf'})
        assert conn.hgetall(redis_key) == {'id': '1', 'name': 'asdf'}

        conn.reset_mock()

        # Now try overriding existing value with None! Should do a delete operation
        foo.name = None
        foo.save()
        assert conn.mock_calls == [call.hdel(redis_key, 'name')]
        assert conn.hgetall(redis_key) == {'id': '1'}

    def test_none_field_mixed(self, conn, pipe):
        """
        Try saving a real value and a None value at same time
        """
        class Foo(Model):
            a = fields.CharField()
            b = fields.CharField()

        foo = Foo(id=1, a='foo', b='bar')
        foo.save()
        data = conn.hgetall('foo:1')
        assert data == {'id': '1', 'a': 'foo', 'b': 'bar'}

        foo = Foo.get(1)
        foo.a = 'alpha'
        foo.b = None
        foo.save()

        assert conn.mock_calls[-1] == call.pipeline()

        pipe.hmset.assert_called_with('foo:1', {'a': 'alpha'})

        pipe.hdel.assert_called_with('foo:1', 'b')

        # Check what's in redis
        data = conn.hgetall('foo:1')
        assert data == {'id': '1', 'a': 'alpha'}


@pytest.mark.parametrize('save_modified_only', (False, True))
def test_save_modified_only(save_modified_only, conn):
    class Foo(Model):
        name = fields.CharField()
        num = fields.IntegerField()
    Foo.save_modified_only = save_modified_only

    foo = Foo(id=1, name='foo', num=12)
    foo.save()

    foo = Foo.get(1)

    conn.reset_mock()
    foo.name = 'something'
    foo.save()

    if save_modified_only:
        print conn.mock_calls
        conn.hmset.assert_called_once_with('foo:1', {'name': 'something'})

        # next save should do nothing
        foo.save()
        conn.reset_mock()
        assert conn.mock_calls == []
    else:
        data = {'id': '1', 'name': 'something', 'num': '12'}
        conn.hmset.assert_called_once_with('foo:1', data)

        # other saves will still save, sadly
        conn.reset_mock()
        foo.save()
        conn.hmset.assert_called_once_with('foo:1', data)


def test_ttl(conn, pipe):
    class Foo(Model):
        ttl = 30
        name = fields.CharField()

    foo = Foo(id=1, name='foo')
    foo.save()

    # pipe.hmset.assert_called_with('foo:1', {'id': '1', 'name': 'foo'})
    # pipe.expire.assert_called_with('foo:1', 30)
    pipe.assert_called_with('hmset', 'foo:1', {'id': '1', 'name': 'foo'})
    pipe.assert_called_with('expire', 'foo:1', 30)

    foo = Foo.get(id=1)
    assert foo.name == 'foo'


def test_partial_fields(conn, pipe):
    """
    Test that we can selectively load a few fields from Redis, and the unloaded ones will
    get loaded on demand
    """
    class Foo(Model):
        name = fields.CharField()
        num = fields.IntegerField()

    foo = Foo(id=1, name='foo', num=20)
    foo.save()

    foo = Foo.get(id=1, fields=['name'])
    assert foo._loaded_field_names == {'id', 'name'}
    assert pipe.hmget.call_count == 1

    pipe.reset_mocks()

    # access another field
    assert foo.num == 20

    # pipe.assert_called_with('hget', 'foo:1', 'num')
    pipe.hget.assert_called_with('foo:1', 'num')
    assert pipe.hget.call_count == 1

    assert foo._loaded_field_names == {'id', 'name', 'num'}

    # access again
    print foo.num
    assert pipe.hget.call_count == 1


def test_get_multi(Foo, conn, pipe):

    foo1 = Foo(id=1, name='foo', num=10)
    foo1.save()
    foo2 = Foo(id=2, name='bar', num=20)
    foo2.save()

    foos = Foo.get([1, 2])

    assert pipe.hgetall.call_args_list == [
        call('foo:1'),
        call('foo:2'),
    ]

    assert foos[0].id == 1
    assert foos[0].name == 'foo'
    assert foos[1].id == 2

    # Test partial fields access
    pipe.reset_mocks()
    foos = Foo.get([1, 2], fields=['name'])

    assert pipe.hmget.call_count == 2