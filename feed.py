import datetime


class Feed:
    """Minimal implementation of Atom Feed spec."""

    def __init__(self, id_, title, author=None):
        """Init empty feed, set its update datetime to now."""
        self._val_none_or_string(id_)
        self._val_none_or_string(title)
        self._val_none_or_string(author)
        self._id = id_
        self._title = title
        self._author = author
        self._updated = datetime.datetime.utcnow()
        self._entries = []

    def _val_none_or_string(self, val):
        """Ensure val is either None or of string type."""
        if val is not None and type(val) != str:
            msg = 'Non-string value passed where string expected.'
            raise RuntimeError(msg)

    def add_entry(self, id_, title, author=None, content=None, altlink=None):
        """Append to feed entry, ensure validity, reset feed's update datetime.

        If author=None, feed must have been initialized with author be set. One
        of either content or altlink must be set.
        """
        self._val_none_or_string(id_)
        self._val_none_or_string(title)
        self._val_none_or_string(author)
        self._val_none_or_string(content)
        self._val_none_or_string(altlink)
        if self._author is None and author is None:
            msg = 'Entry needs author, since feed has no author set'
            raise RuntimeError(msg)
        if content is None and altlink is None:
            msg = 'One of either content or altlink must be set.'
            raise RuntimeError(msg)
        updated = datetime.datetime.utcnow()
        self._updated = updated
        entry = {
            'id': id_,
            'title': title,
            'updated': updated,
            'author': author,
            'content': content,
            'altlink': altlink
        }
        self._entries += [entry]

    def print(self):
        """Print complete feed as valid XML."""
        import xml.etree.ElementTree as ET

        def add_elem(parent, tag, text=None, attributes={}):
            """Add to parent element <tag>text</tag> attributes."""
            elem = ET.SubElement(parent, tag, attributes)
            if text is not None:
                elem.text = text
            return elem

        def format_datetime(datetime):
            """Format datetime.datetime element to spec-requested format."""
            return datetime.strftime('%Y-%m-%dT%H:%M:%SZ')

        def set_author_if_not_none(parent, source):
            """In parent element, set .author to source if source != None."""
            if source is not None:
                author = add_elem(parent, 'author')
                add_elem(author, 'name', source)

        def prettify(elem):
            """Stringify XML tree of elem to indented form."""
            from xml.dom import minidom
            ugly_xml = ET.tostring(elem, encoding='unicode')
            dom = minidom.parseString(ugly_xml)
            return dom.toprettyxml(indent="  ")

        feed = ET.Element('feed', {'xmlns': 'http://www.w3.org/2005/Atom'})
        add_elem(feed, 'id', self._id)
        add_elem(feed, 'title', self._title)
        add_elem(feed, 'updated', format_datetime(self._updated))
        set_author_if_not_none(feed, self._author)
        for e in self._entries:
            entry = add_elem(feed, 'entry')
            add_elem(entry, 'id', e['id'])
            add_elem(entry, 'title', e['title'])
            add_elem(entry, 'updated', format_datetime(e['updated']))
            set_author_if_not_none(entry, e['author'])
            if e['content'] is not None:
                add_elem(entry, 'content', e['content'])
            if e['altlink'] is not None:
                add_elem(entry, 'link',
                         attributes={'rel': 'alternate', 'href': e['altlink']})
        print(prettify(feed))


f = Feed('foo', 'bar', 'baz')
f.add_entry('FOO', 'BAR', 'BAZ1', 'BAZ2', 'BAZ//&<>3')
f.print()
