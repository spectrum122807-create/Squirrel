import http from 'k6/http';

export default function () {
  http.post('http://127.0.0.1:5000/', {
    username: 'test1',
    password: '1234'
  });

  http.post('http://127.0.0.1:5000/request', {
    title: 'Need charger',
    description: 'Fast',
    budget: '300'
  });
}